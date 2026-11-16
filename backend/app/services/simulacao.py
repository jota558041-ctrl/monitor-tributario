"""Simulador fiscal: cria e altera o 'mundo' fictício consultado nos testes.

Serve a dois propósitos:
 1. permitir usar o sistema de ponta a ponta sem dados reais;
 2. provocar mudanças (homologação, intimação, revogação, novo débito,
    indisponibilidade da fonte) para verificar se os alertas disparam.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.compensacao import Compensacao
from app.models.enums import (
    CategoriaPendencia,
    SituacaoCompensacao,
    SituacaoFiscalGeral,
    SituacaoProcuracao,
)
from app.models.monitoramento import EstadoSimulado
from app.models.procuracao import Procuracao

CENARIOS = {
    "HOMOLOGAR_COMPENSACAO": "Marca a PER/DCOMP como homologada.",
    "HOMOLOGAR_PARCIALMENTE": "Homologação parcial com valor não homologado.",
    "NAO_HOMOLOGAR": "Não homologa a PER/DCOMP e emite despacho decisório.",
    "EMITIR_INTIMACAO": "Gera intimação/exigência com prazo de resposta.",
    "REVERTER_HOMOLOGACAO": "Faz a compensação deixar de constar como homologada.",
    "PARAR_DE_INFORMAR": "Fonte deixa de retornar a PER/DCOMP (sem informação).",
    "REVOGAR_PROCURACAO": "Procuração passa a constar como revogada.",
    "VENCER_PROCURACAO": "Procuração passa a estar vencida.",
    "APROXIMAR_VENCIMENTO": "Procuração vence em N dias (padrão 7).",
    "RENOVAR_PROCURACAO": "Procuração renovada por 12 meses.",
    "NOVO_DEBITO": "Inclui um novo débito na situação fiscal.",
    "QUITAR_DEBITOS": "Zera as pendências da situação fiscal.",
    "REDUZIR_DEBITO": "Reduz o valor de um débito existente.",
    "FONTE_INDISPONIVEL": "Faz a fonte responder INDISPONIVEL.",
    "FONTE_NAO_AUTORIZADA": "Faz a fonte responder NAO_AUTORIZADO (sem poderes).",
    "RESTAURAR_FONTE": "Remove a indisponibilidade forçada.",
}


def _semente(texto: str) -> int:
    return int(hashlib.sha256(texto.encode()).hexdigest()[:8], 16)


def _situacao_sorteada(numero: str) -> str:
    opcoes = [
        SituacaoCompensacao.TRANSMITIDA,
        SituacaoCompensacao.EM_PROCESSAMENTO,
        SituacaoCompensacao.EM_ANALISE,
        SituacaoCompensacao.HOMOLOGADA,
        SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE,
        SituacaoCompensacao.NAO_HOMOLOGADA,
        SituacaoCompensacao.COM_EXIGENCIA,
    ]
    return str(opcoes[_semente(numero) % len(opcoes)])


def obter_estado(db: Session, cliente: Cliente) -> EstadoSimulado | None:
    return db.scalar(select(EstadoSimulado).where(EstadoSimulado.cliente_id == cliente.id))


def semear_estado_de_cliente(
    db: Session, cliente: Cliente, *, sobrescrever: bool = False
) -> EstadoSimulado:
    """Gera estado fictício coerente com o cadastro do cliente."""
    estado = obter_estado(db, cliente)
    if estado is not None and not sobrescrever:
        _completar_estado(db, cliente, estado)
        return estado

    estado = estado or EstadoSimulado(
        organizacao_id=cliente.organizacao_id, cliente_id=cliente.id,
        situacao_fiscal={}, compensacoes={}, procuracoes={},
        nota="Estado fictício gerado automaticamente (ambiente de testes).",
    )
    estado.situacao_fiscal = _situacao_fiscal_inicial(cliente)
    estado.compensacoes = {}
    estado.procuracoes = {}
    db.add(estado)
    db.flush()
    _completar_estado(db, cliente, estado)
    return estado


def _situacao_fiscal_inicial(cliente: Cliente) -> dict[str, Any]:
    semente = _semente(cliente.cnpj)
    perfil = semente % 10
    if perfil in (0, 1, 2):                       # sem pendências
        return {"situacao_geral": str(SituacaoFiscalGeral.REGULAR), "pendencias": [],
                "relatorio_bruto": "Nenhuma pendência encontrada (dados fictícios)."}
    if perfil == 3:                               # fonte indisponível
        return {"forcar": "INDISPONIVEL", "situacao_geral": None, "pendencias": []}
    if perfil == 4:                               # sem poderes
        return {"forcar": "NAO_AUTORIZADO", "situacao_geral": None, "pendencias": []}

    base = Decimal(5000 + (semente % 40) * 250)
    pendencias = [
        {
            "categoria": str(CategoriaPendencia.DEBITO_FEDERAL),
            "codigo": f"{2000 + semente % 900:04d}-01",
            "descricao": "IRPJ - débito declarado em DCTF e não pago",
            "periodo": f"{(semente % 12) + 1:02d}/2024",
            "valor": str(base),
            "situacao": "DEVEDOR",
        },
        {
            "categoria": str(CategoriaPendencia.DEBITO_PREVIDENCIARIO),
            "codigo": f"{1100 + semente % 800:04d}-02",
            "descricao": "Contribuição previdenciária patronal",
            "periodo": f"{(semente % 11) + 1:02d}/2024",
            "valor": str(base / 2),
            "situacao": "EM COBRANÇA",
        },
    ]
    if perfil in (7, 8):
        pendencias.append({
            "categoria": str(CategoriaPendencia.OBRIGACAO_ACESSORIA),
            "codigo": "DCTFWEB-OMISSA",
            "descricao": "Omissão de entrega de DCTFWeb",
            "periodo": f"{(semente % 6) + 1:02d}/2025",
            "valor": "0",
            "situacao": "PENDENTE",
        })
    if perfil == 9:
        pendencias.append({
            "categoria": str(CategoriaPendencia.PARCELAMENTO),
            "codigo": "PARC-2023",
            "descricao": "Parcelamento ordinário em andamento",
            "periodo": "2023",
            "valor": str(base * 2),
            "situacao": "ATIVO",
        })
    return {
        "situacao_geral": str(SituacaoFiscalGeral.COM_PENDENCIAS),
        "pendencias": pendencias,
        "relatorio_bruto": "Relatório fictício de situação fiscal para testes.",
    }


def _completar_estado(db: Session, cliente: Cliente, estado: EstadoSimulado) -> None:
    """Garante que todas as PER/DCOMPs e procurações do cadastro existam na fonte."""
    comps = dict(estado.compensacoes or {})
    for comp in db.scalars(select(Compensacao).where(Compensacao.cliente_id == cliente.id)):
        if comp.numero_perdcomp in comps:
            continue
        situacao = (
            comp.situacao_compensacao
            if comp.situacao_compensacao != SituacaoCompensacao.SEM_INFORMACAO
            else _situacao_sorteada(comp.numero_perdcomp)
        )
        credito = Decimal(str(comp.valor_credito or 0))
        registro: dict[str, Any] = {
            "numero_perdcomp": comp.numero_perdcomp,
            "situacao_compensacao": str(situacao),
            "situacao_declaracao": "ATIVA",
            "data_transmissao": comp.data_transmissao.isoformat() if comp.data_transmissao else None,
            "tributo": comp.tributo,
            "periodo_apuracao": comp.periodo_apuracao,
            "valor_debito": str(comp.valor_debito or credito),
            "valor_credito": str(credito),
            "tem_despacho_decisorio": situacao in (
                str(SituacaoCompensacao.HOMOLOGADA), str(SituacaoCompensacao.NAO_HOMOLOGADA),
                str(SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE),
            ),
            "tem_intimacao": situacao == str(SituacaoCompensacao.COM_EXIGENCIA),
        }
        if situacao == str(SituacaoCompensacao.HOMOLOGADA):
            registro["valor_compensado"] = str(credito)
            registro["resultado_analise"] = "Compensação homologada integralmente (fictício)."
        elif situacao == str(SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE):
            registro["valor_compensado"] = str(credito / 2)
            registro["valor_nao_homologado"] = str(credito / 2)
            registro["resultado_analise"] = "Crédito parcialmente reconhecido (fictício)."
        elif situacao == str(SituacaoCompensacao.NAO_HOMOLOGADA):
            registro["valor_nao_homologado"] = str(credito)
            registro["resultado_analise"] = "Crédito não reconhecido (fictício)."
        elif situacao == str(SituacaoCompensacao.COM_EXIGENCIA):
            registro["prazo_resposta_intimacao"] = (date.today() + timedelta(days=20)).isoformat()
            registro["resultado_analise"] = "Intimação para apresentação de documentos (fictício)."
        comps[comp.numero_perdcomp] = registro
    estado.compensacoes = comps

    procs = dict(estado.procuracoes or {})
    for proc in db.scalars(select(Procuracao).where(Procuracao.cliente_id == cliente.id)):
        chave = proc.numero or proc.id
        if chave in procs:
            continue
        situacao = (
            str(SituacaoProcuracao.EXPIRADA)
            if proc.data_fim and proc.data_fim < date.today()
            else str(SituacaoProcuracao.ATIVA)
        )
        procs[chave] = {
            "numero": proc.numero,
            "situacao": situacao,
            "data_inicio": proc.data_inicio.isoformat() if proc.data_inicio else None,
            "data_fim": proc.data_fim.isoformat() if proc.data_fim else None,
            "procurador_doc": proc.procurador_doc,
            "poderes": ["Consulta de situação fiscal", "Consulta PER/DCOMP", "Caixa Postal"],
            "servicos_autorizados": ["SITFIS", "PERDCOMP", "CAIXA_POSTAL"],
        }
    estado.procuracoes = procs
    db.flush()


def aplicar_cenario(
    db: Session, cliente: Cliente, cenario: str, parametros: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Altera o estado simulado. Devolve descrição do que mudou."""
    if cenario not in CENARIOS:
        raise ValueError(f"Cenário desconhecido: {cenario}. Opções: {', '.join(CENARIOS)}")
    parametros = parametros or {}
    estado = semear_estado_de_cliente(db, cliente)
    comps = dict(estado.compensacoes or {})
    procs = dict(estado.procuracoes or {})
    fiscal = dict(estado.situacao_fiscal or {})
    numero = parametros.get("numero_perdcomp")
    alvo_proc = parametros.get("numero_procuracao")
    mudancas: list[str] = []

    def _chave_comp() -> str | None:
        if numero and numero in comps:
            return numero
        candidatos = [k for k in comps if k != "forcar"]
        return candidatos[0] if candidatos else None

    def _chave_proc() -> str | None:
        if alvo_proc and alvo_proc in procs:
            return alvo_proc
        candidatos = [k for k in procs if k != "forcar"]
        return candidatos[0] if candidatos else None

    if cenario in {"HOMOLOGAR_COMPENSACAO", "HOMOLOGAR_PARCIALMENTE", "NAO_HOMOLOGAR",
                   "EMITIR_INTIMACAO", "REVERTER_HOMOLOGACAO", "PARAR_DE_INFORMAR"}:
        chave = _chave_comp()
        if chave is None:
            raise ValueError("Cliente não possui PER/DCOMP cadastrada para simular.")
        registro = dict(comps[chave])
        credito = Decimal(str(registro.get("valor_credito") or 0))
        if cenario == "HOMOLOGAR_COMPENSACAO":
            registro.update(situacao_compensacao=str(SituacaoCompensacao.HOMOLOGADA),
                            valor_compensado=str(credito), valor_nao_homologado="0",
                            tem_despacho_decisorio=True, tem_intimacao=False,
                            numero_despacho=f"DD-{_semente(chave) % 999999:06d}",
                            data_despacho=date.today().isoformat(),
                            resultado_analise="Compensação homologada integralmente (fictício).")
        elif cenario == "HOMOLOGAR_PARCIALMENTE":
            registro.update(situacao_compensacao=str(SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE),
                            valor_compensado=str(credito / 2),
                            valor_nao_homologado=str(credito / 2),
                            tem_despacho_decisorio=True,
                            data_despacho=date.today().isoformat(),
                            resultado_analise="Homologação parcial (fictício).")
        elif cenario == "NAO_HOMOLOGAR":
            registro.update(situacao_compensacao=str(SituacaoCompensacao.NAO_HOMOLOGADA),
                            valor_compensado="0", valor_nao_homologado=str(credito),
                            tem_despacho_decisorio=True,
                            numero_despacho=f"DD-{_semente(chave) % 999999:06d}",
                            data_despacho=date.today().isoformat(),
                            resultado_analise="Crédito não reconhecido (fictício).")
        elif cenario == "EMITIR_INTIMACAO":
            registro.update(situacao_compensacao=str(SituacaoCompensacao.COM_EXIGENCIA),
                            tem_intimacao=True,
                            prazo_resposta_intimacao=(
                                date.today() + timedelta(days=int(parametros.get("dias", 30)))
                            ).isoformat(),
                            resultado_analise="Intimação emitida (fictício).")
        elif cenario == "REVERTER_HOMOLOGACAO":
            registro.update(situacao_compensacao=str(SituacaoCompensacao.EM_ANALISE),
                            valor_compensado="0", tem_despacho_decisorio=False,
                            resultado_analise="Processo retornou para análise (fictício).")
        elif cenario == "PARAR_DE_INFORMAR":
            comps.pop(chave, None)
            mudancas.append(f"PER/DCOMP {chave} removida da fonte simulada.")
        if cenario != "PARAR_DE_INFORMAR":
            comps[chave] = registro
            mudancas.append(f"PER/DCOMP {chave} -> {registro['situacao_compensacao']}.")

    elif cenario in {"REVOGAR_PROCURACAO", "VENCER_PROCURACAO", "APROXIMAR_VENCIMENTO",
                     "RENOVAR_PROCURACAO"}:
        chave = _chave_proc()
        if chave is None:
            raise ValueError("Cliente não possui procuração cadastrada para simular.")
        registro = dict(procs[chave])
        if cenario == "REVOGAR_PROCURACAO":
            registro["situacao"] = str(SituacaoProcuracao.REVOGADA)
            mudancas.append(f"Procuração {chave} revogada.")
        elif cenario == "VENCER_PROCURACAO":
            registro["situacao"] = str(SituacaoProcuracao.EXPIRADA)
            registro["data_fim"] = (date.today() - timedelta(days=1)).isoformat()
            mudancas.append(f"Procuração {chave} vencida ontem.")
        elif cenario == "APROXIMAR_VENCIMENTO":
            dias = int(parametros.get("dias", 7))
            registro["situacao"] = str(SituacaoProcuracao.ATIVA)
            registro["data_fim"] = (date.today() + timedelta(days=dias)).isoformat()
            mudancas.append(f"Procuração {chave} vence em {dias} dia(s).")
        else:
            registro["situacao"] = str(SituacaoProcuracao.ATIVA)
            registro["data_fim"] = (date.today() + timedelta(days=365)).isoformat()
            mudancas.append(f"Procuração {chave} renovada por 12 meses.")
        procs[chave] = registro

    elif cenario == "NOVO_DEBITO":
        pendencias = list(fiscal.get("pendencias") or [])
        valor = str(parametros.get("valor", "7500.00"))
        pendencias.append({
            "categoria": parametros.get("categoria", str(CategoriaPendencia.DEBITO_FEDERAL)),
            "codigo": parametros.get("codigo", f"NOVO-{_semente(cliente.cnpj) % 9999:04d}"),
            "descricao": parametros.get("descricao", "Débito identificado após compensação"),
            "periodo": parametros.get("periodo", f"{date.today().month:02d}/{date.today().year}"),
            "valor": valor,
            "situacao": "DEVEDOR",
        })
        fiscal.update(pendencias=pendencias, situacao_geral=str(SituacaoFiscalGeral.COM_PENDENCIAS))
        fiscal.pop("forcar", None)
        mudancas.append(f"Novo débito de R$ {valor} incluído.")

    elif cenario == "QUITAR_DEBITOS":
        fiscal.update(pendencias=[], situacao_geral=str(SituacaoFiscalGeral.REGULAR),
                      relatorio_bruto="Nenhuma pendência encontrada (fictício).")
        fiscal.pop("forcar", None)
        mudancas.append("Todas as pendências fiscais foram zeradas.")

    elif cenario == "REDUZIR_DEBITO":
        pendencias = [dict(p) for p in (fiscal.get("pendencias") or [])]
        if not pendencias:
            raise ValueError("Não há pendências para reduzir.")
        fator = Decimal(str(parametros.get("fator", "0.5")))
        alvo = pendencias[0]
        antes = Decimal(str(alvo.get("valor") or 0))
        alvo["valor"] = str((antes * fator).quantize(Decimal("0.01")))
        pendencias[0] = alvo
        fiscal["pendencias"] = pendencias
        fiscal.pop("forcar", None)
        mudancas.append(f"Débito {alvo.get('codigo')} reduzido de {antes} para {alvo['valor']}.")

    elif cenario in {"FONTE_INDISPONIVEL", "FONTE_NAO_AUTORIZADA", "RESTAURAR_FONTE"}:
        dominios = parametros.get("dominios") or ["situacao_fiscal", "compensacoes", "procuracoes"]
        marca = {"FONTE_INDISPONIVEL": "INDISPONIVEL",
                 "FONTE_NAO_AUTORIZADA": "NAO_AUTORIZADO"}.get(cenario)
        for dominio in dominios:
            alvo = {"situacao_fiscal": fiscal, "compensacoes": comps, "procuracoes": procs}[dominio]
            if marca:
                alvo["forcar"] = marca
            else:
                alvo.pop("forcar", None)
        mudancas.append(
            f"Fonte(s) {', '.join(dominios)} -> {marca or 'restaurada(s)'}."
        )

    estado.situacao_fiscal = fiscal
    estado.compensacoes = comps
    estado.procuracoes = procs
    db.flush()
    return {"cenario": cenario, "cliente_id": cliente.id, "cnpj": cliente.cnpj,
            "mudancas": mudancas, "descricao": CENARIOS[cenario]}
