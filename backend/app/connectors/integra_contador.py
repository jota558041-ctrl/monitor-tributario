"""Adaptador para a API Integra Contador (SERPRO) - DESLIGADO por padrão.

O que está documentado publicamente (ver docs/INTEGRACAO_RECEITA_FEDERAL.md):

* A plataforma é comercializada pelo SERPRO ("API Integra Contador") e expõe
  módulos por domínio, entre eles **Integra-SITFIS** (relatório de situação
  fiscal do contribuinte), **Integra-Procurações** (informações de procuração
  eletrônica concedida a terceiros), Integra-CaixaPostal, Integra-DCTFWeb,
  Integra-SN, Integra-MEI, Integra-Sicalc e Integra-Pagamento.
* A autenticação usa Consumer Key + Consumer Secret (Basic, base64 de
  "key:secret") e exige certificado digital **e-CNPJ ICP-Brasil (A1 .p12/.pfx)
  do contratante** na requisição de token; a resposta traz um `jwt_token`
  usado nas chamadas seguintes.
* Quando quem consulta é procurador, há o módulo "Autentica Procurador", com
  Termo de Autorização em XML assinado digitalmente.
* **Não há API oficial pública para consulta de PER/DCOMP.** Os serviços de
  PER/DCOMP (processamento, despacho decisório, intimação) são do portal
  e-CAC. Por isso o domínio de compensações usa importação manual ou
  automação autorizada, nunca um endpoint inventado.

Por que este arquivo não contém URLs/ids de serviço fixos: os identificadores
(`idSistema`/`idServico`) e as URLs pertencem ao catálogo contratual do SERPRO
e mudam de versão para versão. O operador os preenche por variável de
ambiente, a partir da documentação oficial à qual tem acesso. Sem isso, o
conector responde NAO_AUTORIZADO - e o sistema trata como "não consultado",
jamais como "sem pendência".
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Any

from app.connectors.base import CapacidadeFonte, ResultadoConsulta
from app.core.config import settings
from app.models.enums import Disponibilidade, OrigemInformacao

_REF = "docs/INTEGRACAO_RECEITA_FEDERAL.md"


class _RateLimiter:
    """Respeita o limite de chamadas por minuto acordado no contrato."""

    def __init__(self, rpm: int) -> None:
        self.intervalo = 60.0 / max(rpm, 1)
        self._lock = threading.Lock()
        self._ultima = 0.0

    def aguardar(self) -> None:
        with self._lock:
            espera = self.intervalo - (time.monotonic() - self._ultima)
            if espera > 0:
                time.sleep(espera)
            self._ultima = time.monotonic()


class IntegraContadorClient:
    """Cliente HTTP mínimo. Só executa se tudo estiver configurado."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._limiter = _RateLimiter(settings.integra_contador_rate_limit_rpm)

    @property
    def configurado(self) -> bool:
        return bool(
            settings.integra_contador_enabled
            and settings.integra_contador_base_url
            and settings.integra_contador_token_url
            and settings.integra_contador_consumer_key
            and settings.integra_contador_consumer_secret
            and settings.integra_contador_cert_path
        )

    def motivo_indisponibilidade(self) -> str:
        if not settings.integra_contador_enabled:
            return "Integração Integra Contador desativada (MT_INTEGRA_CONTADOR_ENABLED=false)."
        faltando = [
            nome
            for nome, valor in [
                ("MT_INTEGRA_CONTADOR_BASE_URL", settings.integra_contador_base_url),
                ("MT_INTEGRA_CONTADOR_TOKEN_URL", settings.integra_contador_token_url),
                ("MT_INTEGRA_CONTADOR_CONSUMER_KEY", settings.integra_contador_consumer_key),
                ("MT_INTEGRA_CONTADOR_CONSUMER_SECRET", settings.integra_contador_consumer_secret),
                ("MT_INTEGRA_CONTADOR_CERT_PATH", settings.integra_contador_cert_path),
            ]
            if not valor
        ]
        return "Configuração incompleta: " + ", ".join(faltando)

    def _basic_auth(self) -> str:
        par = f"{settings.integra_contador_consumer_key}:{settings.integra_contador_consumer_secret}"
        return base64.b64encode(par.encode()).decode()

    def obter_token(self) -> str:
        """Autenticação mTLS + Basic, conforme modelo documentado pelo SERPRO."""
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        import httpx  # import tardio: só necessário quando a integração está ativa

        cert: Any = settings.integra_contador_cert_path
        if settings.integra_contador_cert_password:
            cert = (settings.integra_contador_cert_path, settings.integra_contador_cert_password)
        with httpx.Client(cert=cert, timeout=60.0) as client:
            resp = client.post(
                settings.integra_contador_token_url,
                headers={
                    "Authorization": f"Basic {self._basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
            )
        resp.raise_for_status()
        corpo = resp.json()
        token = corpo.get("jwt_token") or corpo.get("access_token")
        if not token:
            raise RuntimeError("Resposta de autenticação sem jwt_token/access_token.")
        self._token = token
        self._token_exp = time.time() + int(corpo.get("expires_in", 3600))
        return token

    def consultar(self, *, id_sistema: str, id_servico: str, contribuinte: str,
                  dados: dict[str, Any] | str) -> dict[str, Any]:
        """Chamada genérica ao endpoint de consulta do contrato.

        O envelope (contratante / autorPedidoDados / contribuinte / pedidoDados)
        é o formato documentado; `id_sistema` e `id_servico` vêm do catálogo
        oficial e são informados por configuração.
        """
        import httpx

        token = self.obter_token()
        self._limiter.aguardar()
        payload = {
            "contratante": {"numero": settings.integra_contador_contratante_cnpj, "tipo": 2},
            "autorPedidoDados": {
                "numero": settings.integra_contador_autor_pedido_cnpj
                or settings.integra_contador_contratante_cnpj,
                "tipo": 2,
            },
            "contribuinte": {"numero": contribuinte, "tipo": 2},
            "pedidoDados": {"idSistema": id_sistema, "idServico": id_servico, "dados": dados},
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                settings.integra_contador_base_url.rstrip("/") + "/Consultar",
                headers={"Authorization": f"Bearer {token}", "jwt_token": token,
                         "Content-Type": "application/json"},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json()


_client = IntegraContadorClient()


class _BaseIntegra:
    dominio = "generico"
    env_sistema = ""
    env_servico = ""
    poderes: list[str] = []
    limitacoes: list[str] = []
    disponivel_oficialmente = True

    def __init__(self, db: Any = None) -> None:
        self.db = db
        self.capacidade = CapacidadeFonte(
            nome=f"Integra Contador - {self.dominio}",
            origem=OrigemInformacao.API_INTEGRA_CONTADOR,
            automatizada=self.disponivel_oficialmente,
            requer_certificado=True,
            requer_procuracao=True,
            poderes_necessarios=self.poderes,
            limitacoes=self.limitacoes,
            referencia=_REF,
        )

    def _nao_autorizado(self, motivo: str) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.NAO_AUTORIZADO,
            origem=OrigemInformacao.API_INTEGRA_CONTADOR,
            fonte_descricao=self.capacidade.nome,
            mensagem=motivo,
        )

    def _indisponivel(self, motivo: str) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.INDISPONIVEL,
            origem=OrigemInformacao.API_INTEGRA_CONTADOR,
            fonte_descricao=self.capacidade.nome,
            mensagem=motivo,
        )

    def _executar(self, contribuinte: str, dados: dict[str, Any]) -> ResultadoConsulta:
        import os

        if not self.disponivel_oficialmente:
            return self._nao_autorizado(
                "Não há serviço oficial documentado para este domínio nesta API. "
                "Use importação manual do resultado oficial."
            )
        if not _client.configurado:
            return self._nao_autorizado(_client.motivo_indisponibilidade())
        id_sistema = os.getenv(self.env_sistema, "")
        id_servico = os.getenv(self.env_servico, "")
        if not id_sistema or not id_servico:
            return self._nao_autorizado(
                f"Identificadores de serviço não configurados ({self.env_sistema}/{self.env_servico}). "
                "Preencha com os valores do catálogo oficial do contrato."
            )
        try:
            bruto = _client.consultar(
                id_sistema=id_sistema, id_servico=id_servico,
                contribuinte=contribuinte, dados=dados,
            )
        except Exception as exc:  # noqa: BLE001 - qualquer falha é indisponibilidade
            return self._indisponivel(f"Falha na chamada à API: {type(exc).__name__}: {exc}")
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.OK,
            origem=OrigemInformacao.API_INTEGRA_CONTADOR,
            fonte_descricao=self.capacidade.nome,
            dados=bruto,
            mensagem="Resposta oficial recebida; requer mapeamento conforme contrato.",
        )


class IntegraSituacaoFiscal(_BaseIntegra):
    dominio = "situação fiscal (módulo SITFIS)"
    env_sistema = "MT_IC_SITFIS_ID_SISTEMA"
    env_servico = "MT_IC_SITFIS_ID_SERVICO"
    poderes = ["Consulta de situação fiscal / relatório de situação fiscal"]
    limitacoes = [
        "Exige contrato SERPRO e certificado e-CNPJ A1 do contratante.",
        "Exige procuração eletrônica e-CAC com os serviços correspondentes.",
        "Emissão do relatório é assíncrona (solicitação de protocolo + download).",
        "Sujeito a limite de requisições previsto em contrato.",
    ]

    def consultar(self, *, cnpj: str, contexto: Any = None) -> ResultadoConsulta:
        return self._executar(cnpj, {})


class IntegraProcuracao(_BaseIntegra):
    dominio = "procurações eletrônicas (módulo Procurações)"
    env_sistema = "MT_IC_PROCURACOES_ID_SISTEMA"
    env_servico = "MT_IC_PROCURACOES_ID_SERVICO"
    poderes = ["Consulta de procuração eletrônica concedida a terceiros"]
    limitacoes = [
        "Exige contrato SERPRO e certificado e-CNPJ A1 do contratante.",
        "Retorna dados da procuração concedida ao próprio contratante/procurador.",
    ]

    def consultar(self, *, cnpj: str, numero: str | None = None, contexto: Any = None) -> ResultadoConsulta:
        return self._executar(cnpj, {"numero": numero} if numero else {})


class IntegraCompensacao(_BaseIntegra):
    dominio = "PER/DCOMP"
    disponivel_oficialmente = False
    limitacoes = [
        "NÃO existe API oficial pública de consulta de PER/DCOMP.",
        "Os serviços de PER/DCOMP (processamento, despacho decisório, intimação) "
        "são oferecidos no portal e-CAC, com acesso por certificado/gov.br.",
        "Caminhos legítimos: importar o resultado oficial (PDF/relatório) ou usar "
        "automação de navegador expressamente autorizada pelo titular/procuração.",
        "Não contornar CAPTCHA nem autenticação multifator.",
    ]

    def consultar(self, *, cnpj: str, numero_perdcomp: str, contexto: Any = None) -> ResultadoConsulta:
        return self._executar(cnpj, {"numero": numero_perdcomp})
