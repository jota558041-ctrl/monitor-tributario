"""Schemas compartilhados."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Pagina(BaseModel, Generic[T]):
    itens: list[T]
    total: int
    pagina: int = 1
    tamanho: int = 50

    @property
    def paginas(self) -> int:
        return max(1, -(-self.total // self.tamanho))


class Mensagem(BaseModel):
    detalhe: str
    dados: dict[str, Any] | None = None


class FiltroPadrao(BaseModel):
    busca: str | None = Field(default=None, description="CNPJ, razão social ou nome fantasia")
    responsavel: str | None = None
    tributo: str | None = None
    situacao: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    pagina: int = 1
    tamanho: int = 50
