"""Organização (multi-empresa), usuários e auditoria."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import Perfil


class Organizacao(UUIDPk, Timestamps, Base):
    """Tenant. Toda consulta de dados é segregada por organizacao_id."""
    __tablename__ = "organizacao"

    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    usuarios: Mapped[list[Usuario]] = relationship(back_populates="organizacao")


class Usuario(UUIDPk, Timestamps, Base):
    __tablename__ = "usuario"
    __table_args__ = (UniqueConstraint("organizacao_id", "email", name="uq_usuario_org_email"),)

    organizacao_id: Mapped[str] = mapped_column(ForeignKey("organizacao.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), default=Perfil.ANALISTA, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deve_trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tentativas_falhas: Mapped[int] = mapped_column(default=0, nullable=False)
    # Bloqueio temporário após sucessivas falhas de autenticação
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organizacao: Mapped[Organizacao] = relationship(back_populates="usuarios")


class AuditLog(UUIDPk, Base):
    """Trilha de auditoria: quem fez o quê, quando, de onde.

    Registra leitura de dados sensíveis (LGPD - art. 37) e toda alteração.
    """
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_org_data", "organizacao_id", "created_at"),
        Index("ix_audit_entidade", "entidade", "entidade_id"),
    )

    organizacao_id: Mapped[str | None] = mapped_column(String(32), index=True)
    usuario_id: Mapped[str | None] = mapped_column(String(32), index=True)
    usuario_email: Mapped[str | None] = mapped_column(String(180))
    acao: Mapped[str] = mapped_column(String(60), nullable=False)      # LOGIN, LEITURA, CRIACAO...
    entidade: Mapped[str | None] = mapped_column(String(60))
    entidade_id: Mapped[str | None] = mapped_column(String(64))
    descricao: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    detalhe: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
