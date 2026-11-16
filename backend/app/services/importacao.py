"""Importação de planilhas (.xlsx/.csv) com detecção de colunas e staging.

Fluxo: upload -> detecção/mapeamento -> validação linha a linha -> correção
pelo usuário -> confirmação (gravação com histórico). Nada é gravado no
cadastro antes da confirmação.
"""
from __future__ import annotations

import difflib
import hashlib
import io
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models.cliente import Cliente
from app.models.enums import (
    AcaoLinha,
    OrigemInformacao,
    SituacaoCompensacao,
    StatusImportacao,
)
from app.models.importacao import Importacao, ImportacaoLinha
from app.services import clientes as svc_clientes
from app.services.cnpj import cnpj_valido, documento_valido, limpar
from app.services.parsers import (
    normalizar_cabecalho,
    parse_data,
    parse_decimal,
    parse_periodo,
    texto_ou_none,
)


@dataclass(frozen=True)
class CampoImportacao:
    nome: str
    label: str
    tipo: str                 # texto | cnpj | documento | data | decimal | periodo
    sinonimos: tuple[str, ...]
    obrigatorio: bool = False
    entidade: str = "cliente"  # cliente | procuracao | compensacao


CAMPOS: tuple[CampoImportacao, ...] = (
    CampoImportacao("cnpj", "CNPJ", "cnpj",
                    ("cnpj", "cnpj cliente", "cnpj da empresa", "documento", "cnpj cpf",
                     "numero cnpj", "cnpj do contribuinte"), obrigatorio=True),
    CampoImportacao("razao_social", "Razão social", "texto",
                    ("razao social", "razao", "empresa", "nome empresarial", "nome da empresa",
                     "cliente", "nome")),
    CampoImportacao("nome_fantasia", "Nome fantasia", "texto",
                    ("nome fantasia", "fantasia", "nome comercial")),
    CampoImportacao("email", "E-mail", "texto",
                    ("email", "e mail", "e mail contato", "email cliente", "contato email")),
    CampoImportacao("responsavel", "Responsável", "texto",
                    ("responsavel", "responsavel pelo cliente", "analista", "gestor",
                     "responsavel interno", "consultor")),
    CampoImportacao("telefone", "Telefone", "texto", ("telefone", "fone", "celular", "whatsapp")),
    CampoImportacao("tributos_trabalhados", "Tributos trabalhados", "texto",
                    ("tributos trabalhados", "tributos", "tributo trabalhado", "impostos")),
    CampoImportacao("numero_procuracao", "Número da procuração", "texto",
                    ("numero da procuracao", "numero procuracao", "procuracao", "n procuracao",
                     "codigo procuracao", "id procuracao"), entidade="procuracao"),
    CampoImportacao("procurador_doc", "CPF/CNPJ do procurador", "documento",
                    ("cpf do procurador", "cnpj do procurador", "procurador", "documento procurador",
                     "cpf cnpj procurador"), entidade="procuracao"),
    CampoImportacao("data_inicio_procuracao", "Início da procuração", "data",
                    ("data de inicio da procuracao", "inicio procuracao", "data inicio procuracao",
                     "inicio da procuracao", "data inicio"), entidade="procuracao"),
    CampoImportacao("validade_procuracao", "Validade da procuração", "data",
                    ("data de validade da procuracao", "validade da procuracao", "validade procuracao",
                     "vencimento procuracao", "data vencimento procuracao", "validade",
                     "data de validade", "fim procuracao"), entidade="procuracao"),
    CampoImportacao("numero_perdcomp", "Número da PER/DCOMP", "texto",
                    ("numero da per dcomp", "numero per dcomp", "per dcomp", "perdcomp",
                     "numero perdcomp", "n perdcomp", "declaracao de compensacao",
                     "numero da declaracao"), entidade="compensacao"),
    CampoImportacao("tributo", "Tributo da compensação", "texto",
                    ("tributo", "tributo compensado", "tributo da compensacao", "codigo receita"),
                    entidade="compensacao"),
    CampoImportacao("periodo_apuracao", "Período de apuração", "periodo",
                    ("periodo de apuracao", "periodo apuracao", "pa", "competencia",
                     "periodo"), entidade="compensacao"),
    CampoImportacao("valor_compensacao", "Valor da compensação", "decimal",
                    ("valor da compensacao", "valor compensacao", "valor compensado",
                     "valor do credito", "valor credito", "credito utilizado", "valor"),
                    entidade="compensacao"),
    CampoImportacao("valor_debito", "Valor do débito", "decimal",
                    ("valor do debito", "valor debito", "debito"), entidade="compensacao"),
    CampoImportacao("data_operacao", "Data da operação", "data",
                    ("data da operacao", "data operacao", "data de transmissao",
                     "data transmissao", "data envio", "data"), entidade="compensacao"),
    CampoImportacao("situacao_compensacao_informada", "Situação informada da compensação", "texto",
                    ("situacao da compensacao", "situacao compensacao", "status compensacao",
                     "situacao"), entidade="compensacao"),
)

CAMPOS_POR_NOME = {c.nome: c for c in CAMPOS}

_MAPA_SITUACAO_TEXTO = {
    "transmitida": SituacaoCompensacao.TRANSMITIDA,
    "transmitido": SituacaoCompensacao.TRANSMITIDA,
    "enviada": SituacaoCompensacao.TRANSMITIDA,
    "em processamento": SituacaoCompensacao.EM_PROCESSAMENTO,
    "processamento": SituacaoCompensacao.EM_PROCESSAMENTO,
    "em analise": SituacaoCompensacao.EM_ANALISE,
    "analise": SituacaoCompensacao.EM_ANALISE,
    "homologada": SituacaoCompensacao.HOMOLOGADA,
    "deferida": SituacaoCompensacao.HOMOLOGADA,
    "nao homologada": SituacaoCompensacao.NAO_HOMOLOGADA,
    "indeferida": SituacaoCompensacao.NAO_HOMOLOGADA,
    "homologada parcialmente": SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE,
    "parcialmente homologada": SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE,
    "deferida parcialmente": SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE,
    "cancelada": SituacaoCompensacao.CANCELADA,
    "com exigencia": SituacaoCompensacao.COM_EXIGENCIA,
    "intimacao": SituacaoCompensacao.COM_EXIGENCIA,
    "com intimacao": SituacaoCompensacao.COM_EXIGENCIA,
    "exigencia": SituacaoCompensacao.COM_EXIGENCIA,
}


def normalizar_situacao_texto(valor: Any) -> SituacaoCompensacao | None:
    from app.services.parsers import sem_acento

    texto = texto_ou_none(valor)
    if not texto:
        return None
    chave = normalizar_cabecalho(sem_acento(texto))
    return _MAPA_SITUACAO_TEXTO.get(chave)


# ----------------------------------------------------------------- leitura ---
def ler_tabela(conteudo: bytes, nome_arquivo: str) -> pd.DataFrame:
    nome = (nome_arquivo or "").lower()
    if nome.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(conteudo), dtype=object, engine="openpyxl")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        for sep in (None, ";", ",", "\t"):
            try:
                df = pd.read_csv(
                    io.BytesIO(conteudo), dtype=object, encoding=encoding,
                    sep=sep, engine="python",
                )
            except Exception:  # noqa: BLE001
                continue
            if df.shape[1] > 1 or sep is None:
                if df.shape[1] > 1:
                    return df
    raise ValueError("Não foi possível interpretar o arquivo. Use .xlsx ou .csv válido.")


def detectar_colunas(colunas: list[str]) -> tuple[dict[str, str], list[str]]:
    """Mapeia coluna da planilha -> campo do sistema.

    Estratégia: correspondência exata do cabeçalho normalizado, depois
    sinônimos, depois similaridade textual (>= 0,86). Colunas não reconhecidas
    são devolvidas para o usuário decidir.
    """
    mapeamento: dict[str, str] = {}
    ignoradas: list[str] = []
    usados: set[str] = set()

    indice: dict[str, str] = {}
    for campo in CAMPOS:
        indice[normalizar_cabecalho(campo.nome)] = campo.nome
        indice[normalizar_cabecalho(campo.label)] = campo.nome
        for sin in campo.sinonimos:
            indice.setdefault(normalizar_cabecalho(sin), campo.nome)

    for coluna in colunas:
        chave = normalizar_cabecalho(coluna)
        if not chave:
            ignoradas.append(coluna)
            continue
        campo = indice.get(chave)
        if campo is None:
            similares = difflib.get_close_matches(chave, list(indice.keys()), n=1, cutoff=0.86)
            campo = indice[similares[0]] if similares else None
        if campo is None or campo in usados:
            ignoradas.append(coluna)
            continue
        mapeamento[coluna] = campo
        usados.add(campo)
    return mapeamento, ignoradas


def _converter(campo: CampoImportacao, valor: Any) -> Any:
    if campo.tipo == "data":
        d = parse_data(valor)
        return d.isoformat() if d else None
    if campo.tipo == "decimal":
        n = parse_decimal(valor)
        return str(n) if n is not None else None
    if campo.tipo == "periodo":
        return parse_periodo(valor)
    if campo.tipo in {"cnpj", "documento"}:
        return limpar(texto_ou_none(valor)) or None
    return texto_ou_none(valor)


def _validar_linha(dados: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    erros: list[dict[str, str]] = []
    avisos: list[dict[str, str]] = []

    cnpj = dados.get("cnpj")
    if not cnpj:
        erros.append({"campo": "cnpj", "mensagem": "CNPJ não informado."})
    elif len(cnpj) != 14:
        erros.append({"campo": "cnpj", "mensagem": f"CNPJ com {len(cnpj)} dígitos (esperado 14)."})
    elif not cnpj_valido(cnpj):
        erros.append({"campo": "cnpj", "mensagem": "CNPJ inválido (dígitos verificadores)."})

    if not dados.get("razao_social"):
        avisos.append({"campo": "razao_social", "mensagem": "Razão social ausente."})

    email = dados.get("email")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        avisos.append({"campo": "email", "mensagem": f"E-mail possivelmente inválido: {email}"})

    proc_doc = dados.get("procurador_doc")
    if proc_doc and not documento_valido(proc_doc):
        avisos.append({"campo": "procurador_doc", "mensagem": "CPF/CNPJ do procurador inválido."})

    tem_proc = any(dados.get(c) for c in ("numero_procuracao", "validade_procuracao", "procurador_doc"))
    if tem_proc and not dados.get("validade_procuracao"):
        avisos.append({
            "campo": "validade_procuracao",
            "mensagem": "Procuração informada sem data de validade; situação ficará DESCONHECIDA.",
        })
    validade = parse_data(dados.get("validade_procuracao"))
    inicio = parse_data(dados.get("data_inicio_procuracao"))
    if validade and inicio and validade < inicio:
        erros.append({"campo": "validade_procuracao", "mensagem": "Validade anterior à data de início."})
    if validade and validade < date.today():
        avisos.append({
            "campo": "validade_procuracao",
            "mensagem": f"Validade informada já vencida ({validade.isoformat()}). "
                        "Será necessário validar por fonte autorizada.",
        })

    numero_perdcomp = dados.get("numero_perdcomp")
    if numero_perdcomp:
        if not dados.get("valor_compensacao"):
            avisos.append({"campo": "valor_compensacao", "mensagem": "PER/DCOMP sem valor de compensação."})
        if not dados.get("data_operacao"):
            avisos.append({"campo": "data_operacao", "mensagem": "PER/DCOMP sem data da operação/transmissão."})
        situacao_txt = dados.get("situacao_compensacao_informada")
        if situacao_txt and normalizar_situacao_texto(situacao_txt) is None:
            avisos.append({
                "campo": "situacao_compensacao_informada",
                "mensagem": f"Situação '{situacao_txt}' não reconhecida; será tratada como SEM_INFORMACAO.",
            })
    valor_comp = dados.get("valor_compensacao")
    if valor_comp and float(valor_comp) <= 0:
        avisos.append({"campo": "valor_compensacao", "mensagem": "Valor de compensação menor ou igual a zero."})
    return erros, avisos


def criar_importacao(
    db: Session, *, organizacao_id: str, usuario_id: str | None, usuario_email: str | None,
    nome_arquivo: str, conteudo: bytes, mapeamento_manual: dict[str, str] | None = None,
) -> Importacao:
    df = ler_tabela(conteudo, nome_arquivo)
    df = df.dropna(how="all")
    colunas = [str(c) for c in df.columns]
    mapeamento, ignoradas = detectar_colunas(colunas)
    if mapeamento_manual:
        for coluna, campo in mapeamento_manual.items():
            if campo in CAMPOS_POR_NOME:
                mapeamento[coluna] = campo
                if coluna in ignoradas:
                    ignoradas.remove(coluna)
            elif campo in ("", None):
                mapeamento.pop(coluna, None)

    importacao = Importacao(
        organizacao_id=organizacao_id,
        usuario_id=usuario_id,
        usuario_email=usuario_email,
        arquivo_nome=nome_arquivo,
        arquivo_hash=hashlib.sha256(conteudo).hexdigest(),
        status=StatusImportacao.RASCUNHO,
        total_linhas=int(len(df)),
        mapeamento=mapeamento,
        colunas_detectadas=colunas,
        colunas_ignoradas=ignoradas,
    )
    db.add(importacao)
    db.flush()

    vistos_perdcomp: dict[tuple[str, str], int] = {}
    cnpjs_na_planilha: dict[str, int] = {}
    existentes = {
        c.cnpj: c.id
        for c in db.scalars(select(Cliente).where(Cliente.organizacao_id == organizacao_id))
    }

    for pos, (_, linha_df) in enumerate(df.iterrows(), start=2):
        brutos = {str(k): (None if pd.isna(v) else v) for k, v in linha_df.items()}
        dados: dict[str, Any] = {}
        for coluna, campo_nome in mapeamento.items():
            if coluna in brutos:
                dados[campo_nome] = _converter(CAMPOS_POR_NOME[campo_nome], brutos[coluna])
        erros, avisos = _validar_linha(dados)

        acao = AcaoLinha.ERRO if erros else AcaoLinha.CRIAR
        duplicada_de: int | None = None
        cnpj = dados.get("cnpj")
        cliente_id = existentes.get(cnpj) if cnpj else None

        if not erros and cnpj:
            numero = dados.get("numero_perdcomp")
            if numero:
                chave = (cnpj, str(numero))
                if chave in vistos_perdcomp:
                    acao = AcaoLinha.DUPLICADO
                    duplicada_de = vistos_perdcomp[chave]
                    avisos.append({
                        "campo": "numero_perdcomp",
                        "mensagem": f"PER/DCOMP repetida na planilha (linha {duplicada_de}).",
                    })
                else:
                    vistos_perdcomp[chave] = pos
            if cnpj in cnpjs_na_planilha and acao != AcaoLinha.DUPLICADO:
                avisos.append({
                    "campo": "cnpj",
                    "mensagem": f"CNPJ também presente na linha {cnpjs_na_planilha[cnpj]} "
                                "(as informações serão consolidadas no mesmo cliente).",
                })
            cnpjs_na_planilha.setdefault(cnpj, pos)
            if cliente_id and acao == AcaoLinha.CRIAR:
                acao = AcaoLinha.ATUALIZAR

        db.add(
            ImportacaoLinha(
                importacao_id=importacao.id,
                numero_linha=pos,
                dados_brutos={k: (str(v) if v is not None else None) for k, v in brutos.items()},
                dados_normalizados=dados,
                erros=erros,
                avisos=avisos,
                acao=acao,
                selecionada=acao != AcaoLinha.ERRO,
                cliente_id=cliente_id,
                duplicada_de_linha=duplicada_de,
            )
        )

    db.flush()
    importacao.resumo = resumir(db, importacao)
    importacao.status = StatusImportacao.VALIDADO
    db.flush()
    return importacao


def resumir(db: Session, importacao: Importacao) -> dict[str, Any]:
    linhas = db.scalars(
        select(ImportacaoLinha).where(ImportacaoLinha.importacao_id == importacao.id)
    ).all()
    por_acao: dict[str, int] = {}
    for linha in linhas:
        por_acao[linha.acao] = por_acao.get(linha.acao, 0) + 1
    return {
        "total_linhas": len(linhas),
        "por_acao": por_acao,
        "com_erro": sum(1 for x in linhas if x.erros),
        "com_aviso": sum(1 for x in linhas if x.avisos),
        "selecionadas": sum(1 for x in linhas if x.selecionada),
        "clientes_distintos": len({x.dados_normalizados.get("cnpj") for x in linhas
                                   if x.dados_normalizados.get("cnpj")}),
        "perdcomps": sum(1 for x in linhas if x.dados_normalizados.get("numero_perdcomp")),
        "procuracoes": sum(1 for x in linhas if x.dados_normalizados.get("numero_procuracao")
                           or x.dados_normalizados.get("validade_procuracao")),
    }


def corrigir_linha(
    db: Session, linha: ImportacaoLinha, correcoes: dict[str, Any],
    *, organizacao_id: str, selecionada: bool | None = None,
) -> ImportacaoLinha:
    dados = dict(linha.dados_normalizados or {})
    for campo_nome, valor in correcoes.items():
        campo = CAMPOS_POR_NOME.get(campo_nome)
        if campo is None:
            continue
        dados[campo_nome] = _converter(campo, valor)
    erros, avisos = _validar_linha(dados)
    linha.dados_normalizados = dados
    linha.erros = erros
    linha.avisos = avisos
    linha.corrigida = True
    cnpj = dados.get("cnpj")
    cliente = (
        svc_clientes.buscar_por_cnpj(db, organizacao_id, cnpj) if cnpj and not erros else None
    )
    linha.cliente_id = cliente.id if cliente else None
    if erros:
        linha.acao = AcaoLinha.ERRO
        linha.selecionada = False
    elif linha.acao in (AcaoLinha.ERRO, AcaoLinha.CRIAR, AcaoLinha.ATUALIZAR):
        linha.acao = AcaoLinha.ATUALIZAR if cliente else AcaoLinha.CRIAR
        linha.selecionada = True if selecionada is None else selecionada
    if selecionada is not None:
        linha.selecionada = selecionada
    db.flush()
    return linha


def confirmar(
    db: Session, importacao: Importacao, *, usuario_id: str | None, usuario_email: str | None,
    criar_estado_simulado: bool | None = None,
) -> dict[str, Any]:
    """Grava no cadastro as linhas selecionadas e sem erro.

    Idempotente por linha: cliente, procuração e PER/DCOMP sofrem upsert.
    Toda alteração gera registro em cliente_historico / compensacao_evento.
    """
    from app.core.config import settings as _settings
    from app.services import compensacoes as svc_comp
    from app.services import procuracoes as svc_proc
    from app.services.simulacao import semear_estado_de_cliente

    if importacao.status == StatusImportacao.CONFIRMADO:
        raise ValueError("Importação já confirmada.")
    if importacao.status == StatusImportacao.CANCELADO:
        raise ValueError("Importação cancelada não pode ser confirmada.")

    if criar_estado_simulado is None:
        criar_estado_simulado = (
            _settings.connector_situacao_fiscal == "simulador"
            or _settings.connector_compensacao == "simulador"
        )

    linhas = db.scalars(
        select(ImportacaoLinha)
        .where(ImportacaoLinha.importacao_id == importacao.id)
        .order_by(ImportacaoLinha.numero_linha)
    ).all()

    criados = atualizados = ignorados = com_erro = 0
    procuracoes_novas = compensacoes_novas = 0
    clientes_tocados: dict[str, Cliente] = {}
    detalhes: list[dict[str, Any]] = []

    for linha in linhas:
        if linha.erros:
            com_erro += 1
            linha.resultado = "Linha com erro: não importada."
            continue
        if not linha.selecionada or linha.acao in (AcaoLinha.IGNORAR, AcaoLinha.DUPLICADO):
            ignorados += 1
            linha.resultado = f"Linha não importada (ação={linha.acao})."
            continue

        dados = dict(linha.dados_normalizados or {})
        cnpj = dados["cnpj"]
        cliente = clientes_tocados.get(cnpj) or svc_clientes.buscar_por_cnpj(
            db, importacao.organizacao_id, cnpj
        )
        if cliente is None:
            cliente = svc_clientes.criar_cliente(
                db, organizacao_id=importacao.organizacao_id, cnpj=cnpj, dados=dados,
                origem=OrigemInformacao.PLANILHA, usuario_id=usuario_id, usuario_email=usuario_email,
            )
            criados += 1
            acao_cliente = "criado"
        else:
            alterados = svc_clientes.atualizar_cliente(
                db, cliente, dados, origem=OrigemInformacao.PLANILHA,
                usuario_id=usuario_id, usuario_email=usuario_email,
            )
            atualizados += 1
            acao_cliente = f"atualizado ({len(alterados)} campo(s))"
        clientes_tocados[cnpj] = cliente
        linha.cliente_id = cliente.id

        resumo_linha: dict[str, Any] = {"linha": linha.numero_linha, "cnpj": cnpj,
                                        "cliente": acao_cliente}

        if dados.get("numero_procuracao") or dados.get("validade_procuracao"):
            _, nova = svc_proc.upsert_procuracao(
                db, cliente,
                {
                    "numero": dados.get("numero_procuracao"),
                    "data_fim": dados.get("validade_procuracao"),
                    "data_inicio": dados.get("data_inicio_procuracao"),
                    "procurador_doc": dados.get("procurador_doc"),
                },
                origem=OrigemInformacao.PLANILHA,
            )
            procuracoes_novas += int(nova)
            resumo_linha["procuracao"] = "criada" if nova else "atualizada"

        if dados.get("numero_perdcomp"):
            situacao_inicial = normalizar_situacao_texto(
                dados.get("situacao_compensacao_informada")
            )
            _, nova = svc_comp.upsert_compensacao(
                db, cliente,
                {
                    "numero_perdcomp": dados["numero_perdcomp"],
                    "data_transmissao": dados.get("data_operacao"),
                    "tributo": dados.get("tributo") or dados.get("tributos_trabalhados"),
                    "periodo_apuracao": dados.get("periodo_apuracao"),
                    "valor_credito": dados.get("valor_compensacao"),
                    "valor_debito": dados.get("valor_debito"),
                    "situacao_compensacao": situacao_inicial,
                },
                origem=OrigemInformacao.PLANILHA, usuario_email=usuario_email,
            )
            compensacoes_novas += int(nova)
            resumo_linha["perdcomp"] = ("criada" if nova else "atualizada") + (
                f" [{situacao_inicial}]" if situacao_inicial else " [SEM_INFORMACAO]"
            )

        linha.resultado = "; ".join(f"{k}={v}" for k, v in resumo_linha.items() if k != "linha")
        detalhes.append(resumo_linha)

    if criar_estado_simulado:
        for cliente in clientes_tocados.values():
            semear_estado_de_cliente(db, cliente)

    importacao.status = StatusImportacao.CONFIRMADO
    importacao.confirmado_em = utcnow()
    resumo = {
        **resumir(db, importacao),
        "clientes_criados": criados,
        "clientes_atualizados": atualizados,
        "linhas_ignoradas": ignorados,
        "linhas_com_erro": com_erro,
        "procuracoes_criadas": procuracoes_novas,
        "compensacoes_criadas": compensacoes_novas,
        "estado_simulado_gerado": bool(criar_estado_simulado),
        "detalhes": detalhes[:200],
    }
    importacao.resumo = resumo
    db.flush()
    return resumo
