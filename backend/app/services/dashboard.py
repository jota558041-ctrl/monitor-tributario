"""Indicadores do painel administrativo."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alerta import Alerta
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao
from app.models.enums import (
    Criticidade,
    Disponibilidade,
    Semaforo,
    SituacaoCompensacao,
    SituacaoFiscalGeral,
    SituacaoProcuracao,
    StatusAlerta,
)
from app.models.fiscal import SituacaoFiscalSnapshot
from app.models.procuracao import Procuracao
from app.services.procuracoes import semaforo


def _filtrar_clientes(
    consulta: Select, filtros: dict[str, Any]
) -> Select:
    if filtros.get("responsavel"):
        consulta = consulta.where(Cliente.responsavel == filtros["responsavel"])
    if filtros.get("cnpj"):
        consulta = consulta.where(Cliente.cnpj.like(f"%{filtros['cnpj']}%"))
    if filtros.get("razao_social"):
        consulta = consulta.where(Cliente.razao_social.ilike(f"%{filtros['razao_social']}%"))
    return consulta


def resumo(db: Session, organizacao_id: str, filtros: dict[str, Any] | None = None) -> dict[str, Any]:
    filtros = filtros or {}
    agora = datetime.now(UTC)
    limite_frescor = agora - timedelta(days=settings.consulta_desatualizada_dias)

    base_clientes = _filtrar_clientes(
        select(Cliente).where(Cliente.organizacao_id == organizacao_id, Cliente.ativo.is_(True)),
        filtros,
    )
    clientes = list(db.scalars(base_clientes))
    ids = [c.id for c in clientes]

    # ---- compensações -----------------------------------------------------
    comp_q = select(Compensacao.situacao_compensacao, func.count(), func.coalesce(
        func.sum(Compensacao.valor_credito), 0
    )).where(Compensacao.organizacao_id == organizacao_id)
    if ids:
        comp_q = comp_q.where(Compensacao.cliente_id.in_(ids))
    elif filtros:
        comp_q = comp_q.where(Compensacao.cliente_id.in_([]))
    if filtros.get("tributo"):
        comp_q = comp_q.where(Compensacao.tributo == filtros["tributo"])
    if filtros.get("data_inicio"):
        comp_q = comp_q.where(Compensacao.data_transmissao >= filtros["data_inicio"])
    if filtros.get("data_fim"):
        comp_q = comp_q.where(Compensacao.data_transmissao <= filtros["data_fim"])
    por_situacao: dict[str, int] = {str(s): 0 for s in SituacaoCompensacao}
    valor_por_situacao: dict[str, str] = {str(s): "0" for s in SituacaoCompensacao}
    total_comp = 0
    for situacao, qtd, valor in db.execute(comp_q.group_by(Compensacao.situacao_compensacao)):
        por_situacao[str(situacao)] = qtd
        valor_por_situacao[str(situacao)] = str(Decimal(str(valor or 0)))
        total_comp += qtd

    # ---- procurações ------------------------------------------------------
    proc_q = select(Procuracao).where(Procuracao.organizacao_id == organizacao_id)
    if ids:
        proc_q = proc_q.where(Procuracao.cliente_id.in_(ids))
    procuracoes = list(db.scalars(proc_q))
    semaforos = {str(s): 0 for s in Semaforo}
    proc_situacoes = {str(s): 0 for s in SituacaoProcuracao}
    for proc in procuracoes:
        semaforos[str(semaforo(proc))] += 1
        proc_situacoes[str(proc.situacao)] += 1

    # ---- situação fiscal (último snapshot por cliente) --------------------
    com_debitos = sem_pendencia = sem_consulta = indisponivel = 0
    total_debitos = Decimal("0")
    for cliente in clientes:
        snap = db.scalars(
            select(SituacaoFiscalSnapshot)
            .where(SituacaoFiscalSnapshot.cliente_id == cliente.id)
            .order_by(SituacaoFiscalSnapshot.consultado_em.desc())
            .limit(1)
        ).first()
        if snap is None or snap.situacao_geral == SituacaoFiscalGeral.NAO_CONSULTADO:
            sem_consulta += 1
            continue
        if snap.disponibilidade != Disponibilidade.OK:
            indisponivel += 1
            continue
        if snap.situacao_geral == SituacaoFiscalGeral.COM_PENDENCIAS:
            com_debitos += 1
            total_debitos += Decimal(str(snap.total_debitos))
        else:
            sem_pendencia += 1

    desatualizados = sum(
        1 for c in clientes
        if (c.ultima_consulta_fiscal is None
            or (c.ultima_consulta_fiscal.replace(tzinfo=UTC)
                if c.ultima_consulta_fiscal.tzinfo is None else c.ultima_consulta_fiscal) < limite_frescor)
    )

    # ---- alertas ----------------------------------------------------------
    alertas_q = select(Alerta.criticidade, func.count()).where(
        Alerta.organizacao_id == organizacao_id,
        Alerta.status.in_([StatusAlerta.NOVO, StatusAlerta.EM_ANALISE]),
    ).group_by(Alerta.criticidade)
    alertas_por_criticidade = {str(c): 0 for c in Criticidade}
    for criticidade, qtd in db.execute(alertas_q):
        alertas_por_criticidade[str(criticidade)] = qtd

    return {
        "gerado_em": agora.isoformat(),
        "filtros_aplicados": {k: v for k, v in filtros.items() if v},
        "clientes": {
            "total": len(clientes),
            "com_debitos_em_aberto": com_debitos,
            "sem_pendencias_identificadas": sem_pendencia,
            "sem_consulta_atualizada": desatualizados,
            "nunca_consultados": sem_consulta,
            "consulta_indisponivel": indisponivel,
            "total_debitos_em_aberto": str(total_debitos),
        },
        "compensacoes": {
            "total_monitoradas": total_comp,
            "por_situacao": por_situacao,
            "valor_por_situacao": valor_por_situacao,
            "homologadas": por_situacao[str(SituacaoCompensacao.HOMOLOGADA)],
            "em_analise": por_situacao[str(SituacaoCompensacao.EM_ANALISE)]
                          + por_situacao[str(SituacaoCompensacao.EM_PROCESSAMENTO)],
            "nao_homologadas": por_situacao[str(SituacaoCompensacao.NAO_HOMOLOGADA)],
            "homologadas_parcialmente": por_situacao[str(SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE)],
            "com_exigencia": por_situacao[str(SituacaoCompensacao.COM_EXIGENCIA)],
            "sem_informacao": por_situacao[str(SituacaoCompensacao.SEM_INFORMACAO)],
            "transmitidas": por_situacao[str(SituacaoCompensacao.TRANSMITIDA)],
            "canceladas": por_situacao[str(SituacaoCompensacao.CANCELADA)],
        },
        "procuracoes": {
            "total": len(procuracoes),
            "ativas": semaforos[str(Semaforo.VERDE)],
            "proximas_vencimento": semaforos[str(Semaforo.AMARELO)],
            "expiradas_ou_revogadas": semaforos[str(Semaforo.VERMELHO)],
            "situacao_desconhecida": semaforos[str(Semaforo.CINZA)],
            "por_situacao": proc_situacoes,
            "semaforo": semaforos,
        },
        "alertas": {
            "abertos": sum(alertas_por_criticidade.values()),
            "por_criticidade": alertas_por_criticidade,
        },
        "fontes": {
            "procuracao": settings.connector_procuracao,
            "compensacao": settings.connector_compensacao,
            "situacao_fiscal": settings.connector_situacao_fiscal,
            "aviso": (
                "Conectores em modo simulador: dados fictícios, não oriundos da Receita Federal."
                if "simulador" in {settings.connector_procuracao, settings.connector_compensacao,
                                   settings.connector_situacao_fiscal}
                else "Fontes configuradas conforme ambiente."
            ),
        },
    }


def series_temporais(db: Session, organizacao_id: str, dias: int = 90) -> dict[str, Any]:
    """Evolução de débitos totais e de alertas por dia (para gráficos)."""
    inicio = datetime.now(UTC) - timedelta(days=dias)
    snaps = db.scalars(
        select(SituacaoFiscalSnapshot).where(
            SituacaoFiscalSnapshot.organizacao_id == organizacao_id,
            SituacaoFiscalSnapshot.consultado_em >= inicio,
            SituacaoFiscalSnapshot.disponibilidade == Disponibilidade.OK,
        ).order_by(SituacaoFiscalSnapshot.consultado_em)
    ).all()
    por_dia: dict[str, dict[str, Any]] = {}
    for snap in snaps:
        dia = snap.consultado_em.date().isoformat()
        item = por_dia.setdefault(dia, {"data": dia, "total_debitos": Decimal("0"), "consultas": 0,
                                        "clientes": set()})
        item["total_debitos"] += Decimal(str(snap.total_debitos))
        item["consultas"] += 1
        item["clientes"].add(snap.cliente_id)

    alertas = db.execute(
        select(func.date(Alerta.gerado_em), Alerta.criticidade, func.count())
        .where(Alerta.organizacao_id == organizacao_id, Alerta.gerado_em >= inicio)
        .group_by(func.date(Alerta.gerado_em), Alerta.criticidade)
    ).all()
    alertas_dia: dict[str, dict[str, int]] = {}
    for dia, criticidade, qtd in alertas:
        chave = str(dia)[:10]
        alertas_dia.setdefault(chave, {})[str(criticidade)] = qtd

    return {
        "debitos": [
            {"data": v["data"], "total_debitos": str(v["total_debitos"]),
             "consultas": v["consultas"], "clientes": len(v["clientes"])}
            for v in sorted(por_dia.values(), key=lambda x: x["data"])
        ],
        "alertas": [{"data": dia, **valores} for dia, valores in sorted(alertas_dia.items())],
    }
