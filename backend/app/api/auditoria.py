"""Consulta à trilha de auditoria (ADMIN e AUDITOR)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, exige_perfil
from app.models.enums import Perfil
from app.models.tenant import AuditLog, Usuario

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])

PodeAuditar = Annotated[Usuario, Depends(exige_perfil(Perfil.ADMIN, Perfil.AUDITOR))]


@router.get("")
def listar(
    usuario: PodeAuditar, db: DbSession,
    acao: str | None = None, entidade: str | None = None, usuario_email: str | None = None,
    desde: datetime | None = None, ate: datetime | None = None,
    pagina: int = Query(1, ge=1), tamanho: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    consulta = select(AuditLog).where(AuditLog.organizacao_id == usuario.organizacao_id)
    if acao:
        consulta = consulta.where(AuditLog.acao == acao)
    if entidade:
        consulta = consulta.where(AuditLog.entidade == entidade)
    if usuario_email:
        consulta = consulta.where(AuditLog.usuario_email == usuario_email)
    if desde:
        consulta = consulta.where(AuditLog.created_at >= desde)
    if ate:
        consulta = consulta.where(AuditLog.created_at <= ate)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = list(db.scalars(
        consulta.order_by(AuditLog.created_at.desc())
        .offset((pagina - 1) * tamanho).limit(tamanho)
    ))
    return {
        "total": total, "pagina": pagina, "tamanho": tamanho,
        "itens": [
            {"id": i.id, "acao": i.acao, "entidade": i.entidade, "entidade_id": i.entidade_id,
             "usuario_email": i.usuario_email, "descricao": i.descricao, "ip": i.ip,
             "detalhe": i.detalhe, "created_at": i.created_at.isoformat()}
            for i in itens
        ],
    }
