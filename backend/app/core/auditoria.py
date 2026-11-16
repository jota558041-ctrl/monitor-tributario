"""Registro de auditoria (LGPD: rastreabilidade de acesso e alteração)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models.tenant import AuditLog


def registrar(
    db: Session,
    *,
    acao: str,
    organizacao_id: str | None = None,
    usuario_id: str | None = None,
    usuario_email: str | None = None,
    entidade: str | None = None,
    entidade_id: str | None = None,
    descricao: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detalhe: dict[str, Any] | None = None,
    commit: bool = False,
) -> AuditLog:
    log = AuditLog(
        acao=acao,
        organizacao_id=organizacao_id,
        usuario_id=usuario_id,
        usuario_email=usuario_email,
        entidade=entidade,
        entidade_id=entidade_id,
        descricao=descricao,
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
        detalhe=detalhe,
        created_at=utcnow(),
    )
    db.add(log)
    if commit:
        db.commit()
    return log
