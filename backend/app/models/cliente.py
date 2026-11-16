"""Cadastro de clientes e histórico de alterações."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk


class Cliente(UUIDPk, Timestamps, Base):
    __tablename__ = "cliente"
    __table_args__ = (UniqueConstraint("organizacao_id", "cnpj", name="uq_cliente_org_cnpj"),)

    organizacao_id: Mapped[str] = mapped_column(ForeignKey("organizacao.id", ondelete="CASCADE"), index=True)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(180))
    responsavel: Mapped[str | None] = mapped_column(String(180), index=True)
    tributos_trabalhados: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(40))
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Marcadores de frescor de informação (derivados, nunca presumidos)
    ultima_consulta_procuracao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_consulta_compensacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_consulta_fiscal: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    procuracoes: Mapped[list[Procuracao]] = relationship(  # noqa: F821
        back_populates="cliente", cascade="all, delete-orphan"
    )
    compensacoes: Mapped[list[Compensacao]] = relationship(  # noqa: F821
        back_populates="cliente", cascade="all, delete-orphan"
    )
    historico: Mapped[list[ClienteHistorico]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )


class ClienteHistorico(UUIDPk, Base):
    """Histórico campo-a-campo de alterações cadastrais."""
    __tablename__ = "cliente_historico"

    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)
    campo: Mapped[str] = mapped_column(String(60), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_novo: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(String(40), nullable=False)
    usuario_id: Mapped[str | None] = mapped_column(String(32))
    usuario_email: Mapped[str | None] = mapped_column(String(180))
    referencia: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    cliente: Mapped[Cliente] = relationship(back_populates="historico")
