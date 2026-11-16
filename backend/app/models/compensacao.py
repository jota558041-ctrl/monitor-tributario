"""PER/DCOMP: compensações e a linha do tempo de cada uma."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import Disponibilidade, OrigemInformacao, SituacaoCompensacao


class Compensacao(UUIDPk, Timestamps, Base):
    """Uma PER/DCOMP. Vários registros podem apontar para o mesmo CNPJ."""
    __tablename__ = "compensacao"
    __table_args__ = (
        Index("ix_comp_org_situacao", "organizacao_id", "situacao_compensacao"),
        Index("ix_comp_numero", "organizacao_id", "numero_perdcomp"),
    )

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)

    numero_perdcomp: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(30))  # PER, DCOMP, PER/DCOMP
    data_transmissao: Mapped[date | None] = mapped_column(Date, index=True)
    tributo: Mapped[str | None] = mapped_column(String(80), index=True)
    periodo_apuracao: Mapped[str | None] = mapped_column(String(20))   # MM/AAAA ou AAAA
    valor_debito: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_credito: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_compensado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_nao_homologado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    situacao_declaracao: Mapped[str | None] = mapped_column(String(60))   # ex.: ATIVA, RETIFICADA
    situacao_compensacao: Mapped[str] = mapped_column(
        String(40), default=SituacaoCompensacao.SEM_INFORMACAO, nullable=False
    )
    tem_despacho_decisorio: Mapped[bool | None] = mapped_column(Boolean)
    numero_despacho: Mapped[str | None] = mapped_column(String(60))
    data_despacho: Mapped[date | None] = mapped_column(Date)
    tem_intimacao: Mapped[bool | None] = mapped_column(Boolean)
    prazo_resposta_intimacao: Mapped[date | None] = mapped_column(Date)
    resultado_analise: Mapped[str | None] = mapped_column(Text)
    processo_administrativo: Mapped[str | None] = mapped_column(String(40))

    origem_informacao: Mapped[str] = mapped_column(String(40), default=OrigemInformacao.PLANILHA, nullable=False)
    disponibilidade: Mapped[str] = mapped_column(
        String(30), default=Disponibilidade.NAO_CONSULTADO, nullable=False
    )
    consultado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacoes: Mapped[str | None] = mapped_column(Text)

    cliente: Mapped[Cliente] = relationship(back_populates="compensacoes")  # noqa: F821
    eventos: Mapped[list[CompensacaoEvento]] = relationship(
        back_populates="compensacao", cascade="all, delete-orphan",
        order_by="CompensacaoEvento.registrado_em.desc()",
    )


class CompensacaoEvento(UUIDPk, Base):
    """Histórico de evolução: toda consulta e toda mudança de situação."""
    __tablename__ = "compensacao_evento"

    compensacao_id: Mapped[str] = mapped_column(ForeignKey("compensacao.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)  # CONSULTA, MUDANCA_SITUACAO, IMPORTACAO
    situacao_anterior: Mapped[str | None] = mapped_column(String(40))
    situacao_nova: Mapped[str | None] = mapped_column(String(40))
    origem: Mapped[str] = mapped_column(String(40), nullable=False)
    disponibilidade: Mapped[str | None] = mapped_column(String(30))
    mensagem: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64))
    ocorrido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registrado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    criado_por: Mapped[str | None] = mapped_column(String(180))

    compensacao: Mapped[Compensacao] = relationship(back_populates="eventos")
