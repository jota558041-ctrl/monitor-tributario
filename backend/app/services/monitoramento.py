"""Orquestração do monitoramento: consulta as fontes, grava e gera alertas."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.registry import (
    conector_compensacao,
    conector_procuracao,
    conector_situacao_fiscal,
)
from app.core.db import utcnow
from app.ia import analise
from app.ia.achados import Achado
from app.models.alerta import RegraMonitoramento
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao
from app.models.enums import (
    Disponibilidade,
    StatusExecucao,
    TipoMonitoramento,
)
from app.models.monitoramento import ExecucaoMonitoramento
from app.models.procuracao import Procuracao
from app.services import alertas as svc_alertas
from app.services import compensacoes as svc_comp
from app.services import fiscal as svc_fiscal
from app.services import procuracoes as svc_proc


def _clientes(db: Session, organizacao_id: str, ids: list[str] | None) -> list[Cliente]:
    consulta = select(Cliente).where(
        Cliente.organizacao_id == organizacao_id, Cliente.ativo.is_(True)
    )
    if ids:
        consulta = consulta.where(Cliente.id.in_(ids))
    return list(db.scalars(consulta.order_by(Cliente.razao_social)))


def executar(
    db: Session, *, organizacao_id: str, tipo: str = TipoMonitoramento.COMPLETO,
    clientes_ids: list[str] | None = None, acionada_por: str = "AGENDADOR",
    regra: RegraMonitoramento | None = None, usuario_email: str | None = None,
    gerar_alertas: bool = True,
) -> ExecucaoMonitoramento:
    execucao = ExecucaoMonitoramento(
        organizacao_id=organizacao_id,
        tipo=str(tipo),
        status=str(StatusExecucao.EXECUTANDO),
        acionada_por=acionada_por,
        regra_id=regra.id if regra else None,
        iniciado_em=utcnow(),
    )
    db.add(execucao)
    db.flush()

    clientes = _clientes(db, organizacao_id, clientes_ids)
    execucao.total_clientes = len(clientes)
    achados: list[Achado] = []
    detalhe: dict[str, Any] = {"clientes": [], "erros": []}
    ok = indisponiveis = nao_autorizados = mudancas = 0

    faz_proc = tipo in (TipoMonitoramento.PROCURACOES, TipoMonitoramento.COMPLETO)
    faz_comp = tipo in (TipoMonitoramento.COMPENSACOES, TipoMonitoramento.COMPLETO)
    faz_fiscal = tipo in (TipoMonitoramento.SITUACAO_FISCAL, TipoMonitoramento.COMPLETO)

    c_proc = conector_procuracao(db) if faz_proc else None
    c_comp = conector_compensacao(db) if faz_comp else None
    c_fiscal = conector_situacao_fiscal(db) if faz_fiscal else None

    for cliente in clientes:
        linha: dict[str, Any] = {"cliente_id": cliente.id, "cnpj": cliente.cnpj,
                                 "razao_social": cliente.razao_social, "eventos": []}
        try:
            if faz_proc:
                procs = list(db.scalars(
                    select(Procuracao).where(Procuracao.cliente_id == cliente.id)
                ))
                for proc in procs:
                    resultado = c_proc.consultar(cnpj=cliente.cnpj, numero=proc.numero)
                    diff = svc_proc.registrar_consulta(
                        db, proc, resultado, usuario_email=usuario_email
                    )
                    if resultado.disponibilidade == Disponibilidade.OK:
                        ok += 1
                    elif resultado.disponibilidade == Disponibilidade.NAO_AUTORIZADO:
                        nao_autorizados += 1
                    elif resultado.disponibilidade == Disponibilidade.INDISPONIVEL:
                        indisponiveis += 1
                    mudancas += int(bool(diff.get("mudou_situacao")))
                    achados.extend(analise.analisar_procuracao(proc, cliente, diff))
                    linha["eventos"].append({"dominio": "PROCURACAO", "numero": proc.numero,
                                             "disponibilidade": diff["disponibilidade"],
                                             "situacao": diff["situacao_nova"],
                                             "mudou": diff["mudou_situacao"]})

            if faz_comp:
                comps = list(db.scalars(
                    select(Compensacao).where(Compensacao.cliente_id == cliente.id)
                ))
                for comp in comps:
                    resultado = c_comp.consultar(
                        cnpj=cliente.cnpj, numero_perdcomp=comp.numero_perdcomp
                    )
                    diff = svc_comp.registrar_consulta(
                        db, comp, resultado, usuario_email=usuario_email
                    )
                    if resultado.disponibilidade == Disponibilidade.OK:
                        ok += 1
                    elif resultado.disponibilidade == Disponibilidade.NAO_AUTORIZADO:
                        nao_autorizados += 1
                    elif resultado.disponibilidade == Disponibilidade.INDISPONIVEL:
                        indisponiveis += 1
                    mudancas += int(bool(diff.get("mudou_situacao")))
                    achados.extend(analise.analisar_compensacao(comp, cliente, diff))
                    linha["eventos"].append({"dominio": "COMPENSACAO",
                                             "numero": comp.numero_perdcomp,
                                             "disponibilidade": diff["disponibilidade"],
                                             "situacao": diff["situacao_nova"],
                                             "mudou": diff["mudou_situacao"]})

            if faz_fiscal:
                anterior = svc_fiscal.ultimo_snapshot(db, cliente.id)
                resultado = c_fiscal.consultar(cnpj=cliente.cnpj)
                snapshot = svc_fiscal.criar_snapshot(
                    db, cliente, resultado, usuario_email=usuario_email
                )
                if resultado.disponibilidade == Disponibilidade.OK:
                    ok += 1
                elif resultado.disponibilidade == Disponibilidade.NAO_AUTORIZADO:
                    nao_autorizados += 1
                elif resultado.disponibilidade == Disponibilidade.INDISPONIVEL:
                    indisponiveis += 1
                comparativo = None
                if (anterior is not None
                        and snapshot.disponibilidade == Disponibilidade.OK
                        and anterior.hash_conteudo != snapshot.hash_conteudo):
                    # Só grava comparativo quando o conteúdo mudou: consultas
                    # idênticas em sequência não geram histórico redundante.
                    mudancas += 1
                    comparativo = svc_fiscal.comparar(db, cliente, anterior, snapshot)
                comps_cliente = list(db.scalars(
                    select(Compensacao).where(Compensacao.cliente_id == cliente.id)
                ))
                achados.extend(analise.analisar_situacao_fiscal(
                    cliente, snapshot, comparativo, compensacoes_recentes=comps_cliente
                ))
                linha["eventos"].append({
                    "dominio": "SITUACAO_FISCAL",
                    "disponibilidade": snapshot.disponibilidade,
                    "situacao": snapshot.situacao_geral,
                    "total_debitos": str(snapshot.total_debitos),
                    "comparativo": None if comparativo is None else {
                        "diferenca": str(comparativo.diferenca),
                        "novos": len(comparativo.novos or []),
                        "baixados": len(comparativo.baixados or []),
                        "permanecem": len(comparativo.permanecem or []),
                    },
                })

            if tipo == TipoMonitoramento.COMPLETO:
                achados.extend(analise.analisar_frescor(cliente))
        except Exception as exc:  # noqa: BLE001 - um cliente não derruba a execução
            detalhe["erros"].append({"cliente_id": cliente.id, "cnpj": cliente.cnpj,
                                     "erro": f"{type(exc).__name__}: {exc}"})
        detalhe["clientes"].append(linha)

    resultado_alertas = {"criados": 0}
    if gerar_alertas and achados:
        resultado_alertas = svc_alertas.registrar_achados(
            db, organizacao_id, achados, regra=regra
        )

    execucao.consultas_ok = ok
    execucao.consultas_indisponiveis = indisponiveis
    execucao.consultas_nao_autorizadas = nao_autorizados
    execucao.mudancas_detectadas = mudancas
    execucao.alertas_gerados = resultado_alertas.get("criados", 0)
    execucao.detalhe = {**detalhe, "alertas": resultado_alertas,
                        "achados_totais": len(achados)}
    execucao.finalizado_em = utcnow()
    execucao.status = str(
        StatusExecucao.CONCLUIDA_COM_FALHAS
        if detalhe["erros"] or indisponiveis or nao_autorizados
        else StatusExecucao.CONCLUIDA
    )
    if regra is not None:
        regra.ultima_execucao = execucao.finalizado_em
    db.flush()
    return execucao
