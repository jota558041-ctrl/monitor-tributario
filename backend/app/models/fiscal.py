"""Situação fiscal: snapshots imutáveis + comparativo entre consultas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPk
from app.models.enums import SituacaoFiscalGeral


class SituacaoFiscalSnapshot(UUIDPk, Base):
    """Fotografia da situação fiscal em um instante, com proveniência.

    Imutável: nunca sofre UPDATE. Cada consulta gera um novo snapshot, o que
    permite comparação histórica e auditoria.
    """
    __tablename__ = "situacao_fiscal_snapshot"
    __table_args__ = (Index("ix_snap_cliente_data", "cliente_id", "consultado_em"),)

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)

    origem: Mapped[str] = mapped_column(String(40), nullable=False)
    disponibilidade: Mapped[str] = mapped_column(String(30), nullable=False)
    situacao_geral: Mapped[str] = mapped_column(
        String(30), default=SituacaoFiscalGeral.NAO_CONSULTADO, nullable=False
    )
    total_debitos: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_previdenciario: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_federal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_em_cobranca: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_suspenso: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_parcelado: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    qtd_pendencias: Mapped[int] = mapped_column(default=0, nullable=False)
    qtd_obrigacoes_acessorias: Mapped[int] = mapped_column(default=0, nullable=False)

    # Lista de pendências: [{chave, categoria, codigo, descricao, periodo, valor, situacao}]
    pendencias: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    mensagem: Mapped[str | None] = mapped_column(Text)
    relatorio_bruto: Mapped[str | None] = mapped_column(Text)  # texto/base do relatório oficial
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), index=True)
    consultado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    criado_por: Mapped[str | None] = mapped_column(String(180))
    referencia_evento: Mapped[str | None] = mapped_column(String(120))  # ex.: "pos-compensacao"


class SituacaoFiscalComparativo(UUIDPk, Base):
    """Diferença calculada entre dois snapshots - sem inferir causalidade."""
    __tablename__ = "situacao_fiscal_comparativo"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)
    snapshot_anterior_id: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_atual_id: Mapped[str] = mapped_column(String(32), nullable=False)

    total_anterior: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_atual: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    diferenca: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)

    novos: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    baixados: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    permanecem: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    alterados: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Observação textual obrigatória sobre limites de interpretação
    ressalva: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
