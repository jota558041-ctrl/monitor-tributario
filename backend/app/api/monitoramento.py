"""Execução do monitoramento, histórico de execuções e simulador."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, PodeEscrever, UsuarioAtual
from app.core.auditoria import registrar
from app.models.cliente import Cliente
from app.models.monitoramento import ExecucaoMonitoramento
from app.schemas.dominio import ExecucaoOut, MonitorarIn, SimulacaoIn
from app.services import monitoramento as svc
from app.services import simulacao as svc_sim

router = APIRouter(tags=["Monitoramento"])


@router.post("/monitoramento/executar", response_model=dict)
def executar(dados: MonitorarIn, usuario: PodeEscrever, db: DbSession) -> dict[str, Any]:
    execucao = svc.executar(
        db, organizacao_id=usuario.organizacao_id, tipo=dados.tipo,
        clientes_ids=dados.clientes_ids, acionada_por=f"MANUAL:{usuario.email}",
        usuario_email=usuario.email, gerar_alertas=dados.gerar_alertas,
    )
    registrar(db, acao="MONITORAMENTO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="EXECUCAO",
              entidade_id=execucao.id, detalhe={"tipo": execucao.tipo,
                                                "alertas": execucao.alertas_gerados})
    db.commit()
    db.refresh(execucao)
    return {
        "execucao": ExecucaoOut.model_validate(execucao).model_dump(mode="json"),
        "detalhe": execucao.detalhe,
    }


@router.get("/monitoramento/execucoes", response_model=list[ExecucaoOut])
def execucoes(
    usuario: UsuarioAtual, db: DbSession, limite: int = Query(50, ge=1, le=200)
) -> list[ExecucaoMonitoramento]:
    return list(db.scalars(
        select(ExecucaoMonitoramento)
        .where(ExecucaoMonitoramento.organizacao_id == usuario.organizacao_id)
        .order_by(ExecucaoMonitoramento.iniciado_em.desc()).limit(limite)
    ))


@router.get("/monitoramento/execucoes/{execucao_id}")
def execucao_detalhe(execucao_id: str, usuario: UsuarioAtual, db: DbSession) -> dict[str, Any]:
    execucao = db.get(ExecucaoMonitoramento, execucao_id)
    if execucao is None or execucao.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execução não encontrada.")
    return {
        "execucao": ExecucaoOut.model_validate(execucao).model_dump(mode="json"),
        "detalhe": execucao.detalhe,
    }


@router.get("/monitoramento/agendamento")
def agendamento(usuario: UsuarioAtual, db: DbSession) -> dict[str, Any]:
    from app.services.agendador import status_agendador

    return status_agendador()


# ------------------------------------------------------------- simulação ---
@router.get("/simulacao/cenarios")
def cenarios(_: UsuarioAtual) -> list[dict[str, str]]:
    return [{"cenario": k, "descricao": v} for k, v in svc_sim.CENARIOS.items()]


@router.get("/simulacao/estado/{cliente_id}")
def estado(cliente_id: str, usuario: UsuarioAtual, db: DbSession) -> dict[str, Any]:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    estado_simulado = svc_sim.obter_estado(db, cliente)
    if estado_simulado is None:
        return {"cliente_id": cliente_id, "existe": False,
                "aviso": "Nenhum estado simulado. Use /simulacao/semear."}
    return {
        "cliente_id": cliente_id, "existe": True,
        "situacao_fiscal": estado_simulado.situacao_fiscal,
        "compensacoes": estado_simulado.compensacoes,
        "procuracoes": estado_simulado.procuracoes,
        "nota": estado_simulado.nota,
        "atualizado_em": estado_simulado.updated_at.isoformat(),
    }


@router.post("/simulacao/semear")
def semear(
    usuario: PodeEscrever, db: DbSession, cliente_id: str | None = None,
    sobrescrever: bool = False,
) -> dict[str, Any]:
    consulta = select(Cliente).where(Cliente.organizacao_id == usuario.organizacao_id)
    if cliente_id:
        consulta = consulta.where(Cliente.id == cliente_id)
    clientes = list(db.scalars(consulta))
    for cliente in clientes:
        svc_sim.semear_estado_de_cliente(db, cliente, sobrescrever=sobrescrever)
    db.commit()
    return {"clientes_semeados": len(clientes),
            "aviso": "Dados fictícios para teste; não provêm da Receita Federal."}


@router.post("/simulacao/aplicar")
def aplicar(dados: SimulacaoIn, usuario: PodeEscrever, db: DbSession) -> dict[str, Any]:
    cliente = db.get(Cliente, dados.cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    try:
        resultado = svc_sim.aplicar_cenario(db, cliente, dados.cenario, dados.parametros)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    registrar(db, acao="SIMULACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="ESTADO_SIMULADO", entidade_id=cliente.id,
              detalhe=resultado)
    db.commit()
    return {**resultado,
            "proximo_passo": "Execute /monitoramento/executar para detectar as mudanças "
                             "e disparar os alertas."}
