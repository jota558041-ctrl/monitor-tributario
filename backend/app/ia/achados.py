"""Estrutura de um achado: o que foi detectado, por que, com qual evidência."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import Criticidade, TipoAlerta


@dataclass(slots=True)
class Achado:
    tipo: TipoAlerta
    criticidade: Criticidade
    titulo: str
    mensagem: str
    explicacao: str
    dedup_key: str
    cliente_id: str | None = None
    entidade: str | None = None
    entidade_id: str | None = None
    evidencias: list[dict[str, Any]] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "tipo": str(self.tipo),
            "criticidade": str(self.criticidade),
            "titulo": self.titulo,
            "mensagem": self.mensagem,
            "explicacao": self.explicacao,
            "dedup_key": self.dedup_key,
            "cliente_id": self.cliente_id,
            "entidade": self.entidade,
            "entidade_id": self.entidade_id,
            "evidencias": self.evidencias,
        }
