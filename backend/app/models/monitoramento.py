"""Execuções de monitoramento (jobs) e estado do simulador fiscal."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import StatusExecucao


class ExecucaoMonitoramento(UUIDPk, Base):
    __tablename__ = "execucao_monitoramento"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=StatusExecucao.EXECUTANDO, nullable=False)
    acionada_por: Mapped[str] = mapped_column(String(60), default="AGENDADOR", nullable=False)
    regra_id: Mapped[str | None] = mapped_column(String(32))
    total_clientes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultas_ok: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultas_indisponiveis: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultas_nao_autorizadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alertas_gerados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mudancas_detectadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detalhe: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    erro: Mapped[str | None] = mapped_column(Text)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EstadoSimulado(UUIDPk, Timestamps, Base):
    """'Mundo fiscal' fictício usado pelo conector simulador.

    Existe apenas para permitir testar o sistema de ponta a ponta sem dados
    reais e sem tocar em serviços da Receita Federal. Em produção o conector
    simulador deve ser desligado (MT_CONNECTOR_*=manual|integra_contador).
    """
    __tablename__ = "estado_simulado"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    cliente_id: Mapped[str] = mapped_column(ForeignKey("cliente.id", ondelete="CASCADE"), index=True)
    # {"disponibilidade": "...", "situacao_geral": "...", "pendencias": [...]}
    situacao_fiscal: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # {numero_perdcomp: {...}}
    compensacoes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # {numero_procuracao: {...}}
    procuracoes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    nota: Mapped[str | None] = mapped_column(Text)
