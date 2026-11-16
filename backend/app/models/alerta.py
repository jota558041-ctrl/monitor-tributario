"""Alertas, regras de monitoramento e notificações."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import Criticidade, StatusAlerta, StatusNotificacao


class RegraMonitoramento(UUIDPk, Timestamps, Base):
    __tablename__ = "regra_monitoramento"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    tipo_monitoramento: Mapped[str] = mapped_column(String(40), nullable=False)  # TipoMonitoramento
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cron: Mapped[str] = mapped_column(String(60), default="0 6 * * *", nullable=False)
    criticidade_minima: Mapped[str] = mapped_column(String(20), default=Criticidade.BAIXA, nullable=False)
    canais: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["SISTEMA"])
    # None/[] = todos os clientes da organização
    clientes_escopo: Mapped[list[str] | None] = mapped_column(JSON)
    parametros: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    destinatarios: Mapped[list[str] | None] = mapped_column(JSON)
    ultima_execucao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proxima_execucao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Alerta(UUIDPk, Timestamps, Base):
    """Ocorrência detectada. Sempre carrega evidência e data da consulta."""
    __tablename__ = "alerta"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "dedup_key", name="uq_alerta_dedup"),
        Index("ix_alerta_org_status", "organizacao_id", "status"),
    )

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str | None] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    criticidade: Mapped[str] = mapped_column(String(20), default=Criticidade.MEDIA, nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    # Explicação do motivo do alerta (requisito do módulo de IA)
    explicacao: Mapped[str | None] = mapped_column(Text)
    # [{fonte, consultado_em, campo, de, para, referencia, disponibilidade}]
    evidencias: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    entidade: Mapped[str | None] = mapped_column(String(40))    # PROCURACAO, COMPENSACAO, SITUACAO_FISCAL
    entidade_id: Mapped[str | None] = mapped_column(String(32))
    regra_id: Mapped[str | None] = mapped_column(String(32))
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=StatusAlerta.NOVO, nullable=False)
    gerado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolvido_por: Mapped[str | None] = mapped_column(String(180))
    nota_resolucao: Mapped[str | None] = mapped_column(Text)

    notificacoes: Mapped[list[Notificacao]] = relationship(
        back_populates="alerta", cascade="all, delete-orphan"
    )


class Notificacao(UUIDPk, Base):
    __tablename__ = "notificacao"

    alerta_id: Mapped[str] = mapped_column(ForeignKey("alerta.id", ondelete="CASCADE"), index=True)
    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    canal: Mapped[str] = mapped_column(String(20), nullable=False)
    destinatario: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=StatusNotificacao.PENDENTE, nullable=False)
    assunto: Mapped[str | None] = mapped_column(String(255))
    corpo: Mapped[str | None] = mapped_column(Text)
    erro: Mapped[str | None] = mapped_column(Text)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    alerta: Mapped[Alerta] = relationship(back_populates="notificacoes")
