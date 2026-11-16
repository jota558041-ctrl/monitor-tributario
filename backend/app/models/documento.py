"""Documentos anexados (despacho decisório, intimação, relatórios do e-CAC)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPk


class Documento(UUIDPk, Base):
    """Metadados do anexo. O binário fica em volume protegido, fora do banco."""
    __tablename__ = "documento"
    __table_args__ = (
        Index("ix_documento_cliente", "cliente_id", "created_at"),
        Index("ix_documento_entidade", "entidade", "entidade_id"),
    )

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)

    # Vínculo opcional com um registro específico
    entidade: Mapped[str] = mapped_column(String(30), default="CLIENTE", nullable=False)
    entidade_id: Mapped[str | None] = mapped_column(String(32))
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)

    nome_original: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_relativo: Mapped[str] = mapped_column(String(400), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(120), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    descricao: Mapped[str | None] = mapped_column(Text)
    data_documento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Documento restrito só pode ser baixado por ADMIN
    restrito: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    enviado_por: Mapped[str | None] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
