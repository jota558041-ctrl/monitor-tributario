"""Conversão de estruturas para tipos serializáveis em JSON (colunas JSON)."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def para_json(valor: Any) -> Any:
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return str(valor.value)
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, dict):
        return {str(k): para_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [para_json(v) for v in valor]
    return str(valor)
