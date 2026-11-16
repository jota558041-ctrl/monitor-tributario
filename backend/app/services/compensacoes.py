"""PER/DCOMP: gravação, consulta e linha do tempo das compensações."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ResultadoConsulta
from app.core.crypto import content_hash
from app.core.db import utcnow
from app.core.serial import para_json
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao, CompensacaoEvento
from app.models.enums import Disponibilidade, OrigemInformacao, SituacaoCompensacao
from app.services.parsers import parse_data, parse_decimal, parse_periodo, texto_ou_none


def upsert_compensacao(
    db: Session, cliente: Cliente, dados: dict[str, Any],
    *, origem: str = OrigemInformacao.PLANILHA, usuario_email: str | None = None,
) -> tuple[Compensacao, bool]:
    numero = texto_ou_none(dados.get("numero_perdcomp"))
    if not numero:
        raise ValueError("Número da PER/DCOMP é obrigatório.")
    existente = db.scalar(
        select(Compensacao).where(
            Compensacao.organizacao_id == cliente.organizacao_id,
            Compensacao.numero_perdcomp == numero,
            Compensacao.cliente_id == cliente.id,
        )
    )
    criada = existente is None
    comp = existente or Compensacao(
        organizacao_id=cliente.organizacao_id,
        cliente_id=cliente.id,
        numero_perdcomp=numero,
        origem_informacao=str(origem),
        disponibilidade=Disponibilidade.NAO_CONSULTADO,
        situacao_compensacao=SituacaoCompensacao.SEM_INFORMACAO,
    )
    data_transmissao = parse_data(dados.get("data_transmissao"))
    if data_transmissao:
        comp.data_transmissao = data_transmissao
    for campo in ("tributo", "tipo_documento", "situacao_declaracao",
                  "processo_administrativo", "observacoes", "resultado_analise"):
        valor = texto_ou_none(dados.get(campo))
        if valor:
            setattr(comp, campo, valor)
    if dados.get("periodo_apuracao"):
        comp.periodo_apuracao = parse_periodo(dados["periodo_apuracao"])
    for campo in ("valor_debito", "valor_credito", "valor_compensado", "valor_nao_homologado"):
        valor = parse_decimal(dados.get(campo))
        if valor is not None:
            setattr(comp, campo, valor)
    situacao = dados.get("situacao_compensacao")
    if situacao in set(SituacaoCompensacao):
        comp.situacao_compensacao = situacao
    if criada:
        db.add(comp)
        db.flush()
        db.add(
            CompensacaoEvento(
                compensacao_id=comp.id,
                tipo="CADASTRO",
                situacao_anterior=None,
                situacao_nova=comp.situacao_compensacao,
                origem=str(origem),
                disponibilidade=comp.disponibilidade,
                mensagem="Compensação cadastrada a partir de informação declarada.",
                payload=para_json({k: v for k, v in dados.items() if v is not None}),
                registrado_em=utcnow(),
                criado_por=usuario_email,
            )
        )
    db.flush()
    return comp, criada


def _mapear_payload(dados: dict[str, Any]) -> dict[str, Any]:
    """Converte a resposta da fonte no vocabulário interno."""
    situacao = texto_ou_none(dados.get("situacao_compensacao"))
    if situacao not in set(SituacaoCompensacao):
        situacao = None
    return {
        "situacao_compensacao": situacao,
        "situacao_declaracao": texto_ou_none(dados.get("situacao_declaracao")),
        "data_transmissao": parse_data(dados.get("data_transmissao")),
        "tributo": texto_ou_none(dados.get("tributo")),
        "periodo_apuracao": parse_periodo(dados.get("periodo_apuracao")),
        "valor_debito": parse_decimal(dados.get("valor_debito")),
        "valor_credito": parse_decimal(dados.get("valor_credito")),
        "valor_compensado": parse_decimal(dados.get("valor_compensado")),
        "valor_nao_homologado": parse_decimal(dados.get("valor_nao_homologado")),
        "tem_despacho_decisorio": dados.get("tem_despacho_decisorio"),
        "numero_despacho": texto_ou_none(dados.get("numero_despacho")),
        "data_despacho": parse_data(dados.get("data_despacho")),
        "tem_intimacao": dados.get("tem_intimacao"),
        "prazo_resposta_intimacao": parse_data(dados.get("prazo_resposta_intimacao")),
        "resultado_analise": texto_ou_none(dados.get("resultado_analise")),
        "processo_administrativo": texto_ou_none(dados.get("processo_administrativo")),
    }


def registrar_consulta(
    db: Session, comp: Compensacao, resultado: ResultadoConsulta,
    *, usuario_email: str | None = None,
) -> dict[str, Any]:
    """Aplica resultado da consulta, grava evento e devolve o diff."""
    anterior = {
        "situacao_compensacao": comp.situacao_compensacao,
        "tem_despacho_decisorio": comp.tem_despacho_decisorio,
        "tem_intimacao": comp.tem_intimacao,
        "valor_nao_homologado": str(comp.valor_nao_homologado) if comp.valor_nao_homologado else None,
    }
    mudancas: list[dict[str, Any]] = []
    dados = resultado.dados if isinstance(resultado.dados, dict) else None

    if resultado.disponibilidade == Disponibilidade.OK and dados:
        mapeado = _mapear_payload(dados)
        for campo, valor in mapeado.items():
            if valor is None:
                continue
            atual = getattr(comp, campo)
            if isinstance(valor, Decimal) and atual is not None:
                igual = Decimal(str(atual)) == valor
            elif isinstance(valor, date) and isinstance(atual, date):
                igual = atual == valor
            else:
                igual = str(atual) == str(valor)
            if not igual:
                mudancas.append({"campo": campo, "de": str(atual) if atual is not None else None,
                                 "para": str(valor)})
                setattr(comp, campo, valor)
        comp.origem_informacao = str(resultado.origem)
    elif resultado.disponibilidade in (Disponibilidade.INDISPONIVEL, Disponibilidade.NAO_AUTORIZADO):
        # Nunca rebaixar para SEM_INFORMACAO uma situação já conhecida por falha
        # técnica: a informação antiga permanece, marcada como desatualizada.
        pass

    comp.disponibilidade = str(resultado.disponibilidade)
    comp.consultado_em = resultado.consultado_em

    db.add(
        CompensacaoEvento(
            compensacao_id=comp.id,
            tipo="MUDANCA_SITUACAO" if mudancas else "CONSULTA",
            situacao_anterior=anterior["situacao_compensacao"],
            situacao_nova=comp.situacao_compensacao,
            origem=str(resultado.origem),
            disponibilidade=str(resultado.disponibilidade),
            mensagem=resultado.mensagem,
            payload=para_json({"dados": dados, "mudancas": mudancas}) if (dados or mudancas) else None,
            hash_conteudo=content_hash(dados) if dados else None,
            ocorrido_em=resultado.consultado_em,
            registrado_em=utcnow(),
            criado_por=usuario_email,
        )
    )
    cliente = db.get(Cliente, comp.cliente_id)
    if cliente:
        cliente.ultima_consulta_compensacao = resultado.consultado_em
    db.flush()
    return {
        "compensacao_id": comp.id,
        "numero_perdcomp": comp.numero_perdcomp,
        "situacao_anterior": anterior["situacao_compensacao"],
        "situacao_nova": comp.situacao_compensacao,
        "mudou_situacao": anterior["situacao_compensacao"] != comp.situacao_compensacao,
        "mudancas": mudancas,
        "disponibilidade": comp.disponibilidade,
        "evidencia": resultado.para_evidencia(
            entidade="COMPENSACAO", entidade_id=comp.id, numero=comp.numero_perdcomp
        ),
    }
