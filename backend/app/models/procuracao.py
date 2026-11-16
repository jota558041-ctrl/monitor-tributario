"""Procurações eletrônicas e o histórico de consultas a elas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import Disponibilidade, OrigemInformacao, SituacaoProcuracao


class Procuracao(UUIDPk, Timestamps, Base):
    __tablename__ = "procuracao"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)

    numero: Mapped[str | None] = mapped_column(String(60), index=True)
    outorgante_cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    procurador_doc: Mapped[str | None] = mapped_column(String(14))   # CPF ou CNPJ do procurador
    procurador_nome: Mapped[str | None] = mapped_column(String(180))

    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date, index=True)

    # Situação declarada na planilha (não confiável) x situação validada por fonte
    situacao_declarada: Mapped[str] = mapped_column(String(30), default=SituacaoProcuracao.DESCONHECIDA)
    situacao: Mapped[str] = mapped_column(String(30), default=SituacaoProcuracao.DESCONHECIDA, nullable=False)
    poderes: Mapped[list[str] | None] = mapped_column(JSON)
    servicos_autorizados: Mapped[list[str] | None] = mapped_column(JSON)

    origem_informacao: Mapped[str] = mapped_column(String(40), default=OrigemInformacao.PLANILHA, nullable=False)
    disponibilidade: Mapped[str] = mapped_column(
        String(30), default=Disponibilidade.NAO_CONSULTADO, nullable=False
    )
    validada_por_fonte: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consultado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacoes: Mapped[str | None] = mapped_column(Text)

    cliente: Mapped[Cliente] = relationship(back_populates="procuracoes")  # noqa: F821
    consultas: Mapped[list[ProcuracaoConsulta]] = relationship(
        back_populates="procuracao", cascade="all, delete-orphan", order_by="ProcuracaoConsulta.consultado_em.desc()"
    )


class ProcuracaoConsulta(UUIDPk, Base):
    """Cada tentativa de consulta, bem ou mal sucedida, fica registrada."""
    __tablename__ = "procuracao_consulta"

    procuracao_id: Mapped[str] = mapped_column(ForeignKey("procuracao.id", ondelete="CASCADE"), index=True)
    origem: Mapped[str] = mapped_column(String(40), nullable=False)
    disponibilidade: Mapped[str] = mapped_column(String(30), nullable=False)
    situacao_retornada: Mapped[str | None] = mapped_column(String(30))
    data_fim_retornada: Mapped[date | None] = mapped_column(Date)
    mensagem: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64))
    consultado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    criado_por: Mapped[str | None] = mapped_column(String(180))

    procuracao: Mapped[Procuracao] = relationship(back_populates="consultas")
