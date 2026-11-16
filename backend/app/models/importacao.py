"""Importação de planilhas: staging com validação e correção antes do commit."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import AcaoLinha, StatusImportacao


class Importacao(UUIDPk, Timestamps, Base):
    __tablename__ = "importacao"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    usuario_id: Mapped[str | None] = mapped_column(String(32))
    usuario_email: Mapped[str | None] = mapped_column(String(180))
    arquivo_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    arquivo_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default=StatusImportacao.RASCUNHO, nullable=False)
    total_linhas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # {coluna_planilha: campo_sistema}
    mapeamento: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    colunas_detectadas: Mapped[list[str]] = mapped_column(JSON, default=list)
    colunas_ignoradas: Mapped[list[str]] = mapped_column(JSON, default=list)
    resumo: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    linhas: Mapped[list[ImportacaoLinha]] = relationship(
        back_populates="importacao", cascade="all, delete-orphan", order_by="ImportacaoLinha.numero_linha"
    )


class ImportacaoLinha(UUIDPk, Base):
    __tablename__ = "importacao_linha"

    importacao_id: Mapped[str] = mapped_column(ForeignKey("importacao.id", ondelete="CASCADE"), index=True)
    numero_linha: Mapped[int] = mapped_column(Integer, nullable=False)
    dados_brutos: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dados_normalizados: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    erros: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    avisos: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    acao: Mapped[str] = mapped_column(String(20), default=AcaoLinha.CRIAR, nullable=False)
    selecionada: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cliente_id: Mapped[str | None] = mapped_column(String(32))
    duplicada_de_linha: Mapped[int | None] = mapped_column(Integer)
    resultado: Mapped[str | None] = mapped_column(Text)
    corrigida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    importacao: Mapped[Importacao] = relationship(back_populates="linhas")
