"""Situação fiscal: snapshots, comparativos e registro manual."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, PodeEscrever, UsuarioAtual
from app.connectors.base import ResultadoConsulta
from app.connectors.registry import conector_situacao_fiscal
from app.core.auditoria import registrar
from app.core.db import utcnow
from app.models.cliente import Cliente
from app.models.enums import Disponibilidade, OrigemInformacao
from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
from app.schemas.dominio import ComparativoOut, SituacaoFiscalManualIn, SnapshotOut
from app.services import fiscal as svc
from app.services.cnpj import formatar_cnpj

router = APIRouter(prefix="/situacao-fiscal", tags=["Situação fiscal"])


def _cliente(db, cliente_id: str, organizacao_id: str) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return cliente


@router.get("/visao-geral")
def visao_geral(usuario: UsuarioAtual, db: DbSession) -> list[dict[str, Any]]:
    """Último snapshot de cada cliente + variação em relação ao anterior."""
    clientes = list(db.scalars(
        select(Cliente).where(Cliente.organizacao_id == usuario.organizacao_id,
                              Cliente.ativo.is_(True)).order_by(Cliente.razao_social)
    ))
    saida: list[dict[str, Any]] = []
    for cliente in clientes:
        snaps = list(db.scalars(
            select(SituacaoFiscalSnapshot)
            .where(SituacaoFiscalSnapshot.cliente_id == cliente.id)
            .order_by(SituacaoFiscalSnapshot.consultado_em.desc()).limit(2)
        ))
        atual = snaps[0] if snaps else None
        anterior = snaps[1] if len(snaps) > 1 else None
        saida.append({
            "cliente_id": cliente.id,
            "cnpj": formatar_cnpj(cliente.cnpj),
            "razao_social": cliente.razao_social,
            "responsavel": cliente.responsavel,
            "situacao_geral": atual.situacao_geral if atual else "NAO_CONSULTADO",
            "disponibilidade": atual.disponibilidade if atual else "NAO_CONSULTADO",
            "total_debitos": str(atual.total_debitos) if atual else None,
            "qtd_pendencias": atual.qtd_pendencias if atual else None,
            "consultado_em": atual.consultado_em.isoformat() if atual else None,
            "origem": atual.origem if atual else None,
            "total_anterior": str(anterior.total_debitos) if anterior else None,
            "variacao": (str(atual.total_debitos - anterior.total_debitos)
                         if atual and anterior else None),
        })
    return saida


@router.get("/{cliente_id}/snapshots", response_model=list[SnapshotOut])
def snapshots(
    cliente_id: str, usuario: UsuarioAtual, db: DbSession,
    limite: int = Query(30, ge=1, le=200),
) -> list[SituacaoFiscalSnapshot]:
    _cliente(db, cliente_id, usuario.organizacao_id)
    return list(db.scalars(
        select(SituacaoFiscalSnapshot).where(SituacaoFiscalSnapshot.cliente_id == cliente_id)
        .order_by(SituacaoFiscalSnapshot.consultado_em.desc()).limit(limite)
    ))


@router.get("/{cliente_id}/comparativos", response_model=list[ComparativoOut])
def comparativos(
    cliente_id: str, usuario: UsuarioAtual, db: DbSession,
    limite: int = Query(20, ge=1, le=100),
) -> list[SituacaoFiscalComparativo]:
    _cliente(db, cliente_id, usuario.organizacao_id)
    return list(db.scalars(
        select(SituacaoFiscalComparativo)
        .where(SituacaoFiscalComparativo.cliente_id == cliente_id)
        .order_by(SituacaoFiscalComparativo.created_at.desc()).limit(limite)
    ))


@router.post("/{cliente_id}/consultar")
def consultar_agora(cliente_id: str, usuario: PodeEscrever, db: DbSession) -> dict[str, Any]:
    cliente = _cliente(db, cliente_id, usuario.organizacao_id)
    anterior = svc.ultimo_snapshot(db, cliente.id)
    resultado = conector_situacao_fiscal(db).consultar(cnpj=cliente.cnpj)
    snapshot = svc.criar_snapshot(db, cliente, resultado, usuario_email=usuario.email)
    comparativo = None
    if anterior is not None and snapshot.disponibilidade == Disponibilidade.OK:
        comparativo = svc.comparar(db, cliente, anterior, snapshot)
    registrar(db, acao="CONSULTA_FONTE", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="SITUACAO_FISCAL",
              entidade_id=snapshot.id, detalhe={"disponibilidade": snapshot.disponibilidade})
    db.commit()
    db.refresh(snapshot)
    return {
        "snapshot": SnapshotOut.model_validate(snapshot).model_dump(mode="json"),
        "comparativo": (ComparativoOut.model_validate(comparativo).model_dump(mode="json")
                        if comparativo else None),
    }


@router.post("/comparar")
def comparar_manual(
    payload: dict[str, str], usuario: PodeEscrever, db: DbSession
) -> dict[str, Any]:
    """Compara dois snapshots escolhidos pelo usuário."""
    anterior = db.get(SituacaoFiscalSnapshot, payload.get("snapshot_anterior_id", ""))
    atual = db.get(SituacaoFiscalSnapshot, payload.get("snapshot_atual_id", ""))
    if not anterior or not atual or anterior.cliente_id != atual.cliente_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Informe dois snapshots válidos do mesmo cliente.")
    cliente = _cliente(db, atual.cliente_id, usuario.organizacao_id)
    comparativo = svc.comparar(db, cliente, anterior, atual, persistir=False)
    return ComparativoOut.model_validate(comparativo).model_dump(mode="json")


@router.post("/manual", response_model=SnapshotOut, status_code=201)
def registrar_manual(
    dados: SituacaoFiscalManualIn, usuario: PodeEscrever, db: DbSession
) -> SituacaoFiscalSnapshot:
    """Registra situação fiscal obtida manualmente (relatório do e-CAC)."""
    cliente = _cliente(db, dados.cliente_id, usuario.organizacao_id)
    anterior = svc.ultimo_snapshot(db, cliente.id)
    resultado = ResultadoConsulta(
        disponibilidade=Disponibilidade.OK,
        origem=OrigemInformacao.IMPORTACAO_RELATORIO,
        fonte_descricao="Relatório de situação fiscal importado manualmente",
        consultado_em=dados.consultado_em or utcnow(),
        dados={"situacao_geral": str(dados.situacao_geral), "pendencias": dados.pendencias,
               "relatorio_bruto": dados.relatorio_bruto},
        mensagem=f"Informado manualmente por {usuario.email}.",
    )
    snapshot = svc.criar_snapshot(
        db, cliente, resultado, referencia_evento=dados.referencia_evento,
        usuario_email=usuario.email,
    )
    if anterior is not None:
        svc.comparar(db, cliente, anterior, snapshot)
    registrar(db, acao="RESULTADO_MANUAL", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="SITUACAO_FISCAL",
              entidade_id=snapshot.id)
    db.commit()
    db.refresh(snapshot)
    return snapshot
