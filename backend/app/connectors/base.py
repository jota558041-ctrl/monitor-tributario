"""Contrato dos conectores de dados fiscais.

Princípio central: **toda** informação que entra no sistema carrega
proveniência (origem + data/hora da consulta) e um estado técnico de
disponibilidade. Falha de consulta nunca é convertida em "sem pendência".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.core.db import utcnow
from app.models.enums import Disponibilidade, OrigemInformacao


@dataclass(slots=True)
class ResultadoConsulta:
    disponibilidade: Disponibilidade
    origem: OrigemInformacao
    fonte_descricao: str
    consultado_em: datetime = field(default_factory=utcnow)
    dados: Any = None
    mensagem: str | None = None

    @property
    def tem_dados(self) -> bool:
        return self.disponibilidade == Disponibilidade.OK and self.dados is not None

    def para_evidencia(self, **extra: Any) -> dict[str, Any]:
        base = {
            "fonte": self.origem.value,
            "fonte_descricao": self.fonte_descricao,
            "disponibilidade": self.disponibilidade.value,
            "consultado_em": self.consultado_em.isoformat(),
        }
        if self.mensagem:
            base["mensagem"] = self.mensagem
        base.update(extra)
        return base


@dataclass(slots=True)
class CapacidadeFonte:
    """Documentação executável do que cada fonte pode (e não pode) fazer."""
    nome: str
    origem: OrigemInformacao
    automatizada: bool
    requer_certificado: bool
    requer_procuracao: bool
    poderes_necessarios: list[str]
    limitacoes: list[str]
    referencia: str | None = None


@runtime_checkable
class ConectorProcuracao(Protocol):
    capacidade: CapacidadeFonte

    def consultar(self, *, cnpj: str, numero: str | None = None, contexto: Any = None) -> ResultadoConsulta: ...


@runtime_checkable
class ConectorCompensacao(Protocol):
    capacidade: CapacidadeFonte

    def consultar(self, *, cnpj: str, numero_perdcomp: str, contexto: Any = None) -> ResultadoConsulta: ...


@runtime_checkable
class ConectorSituacaoFiscal(Protocol):
    capacidade: CapacidadeFonte

    def consultar(self, *, cnpj: str, contexto: Any = None) -> ResultadoConsulta: ...
