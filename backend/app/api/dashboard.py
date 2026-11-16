"""Painel administrativo: indicadores e séries."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession, UsuarioAtual
from app.services import dashboard as svc

router = APIRouter(prefix="/dashboard", tags=["Painel"])


@router.get("/resumo")
def resumo(
    usuario: UsuarioAtual, db: DbSession,
    cnpj: str | None = None, razao_social: str | None = None,
    responsavel: str | None = None, tributo: str | None = None,
    data_inicio: date | None = None, data_fim: date | None = None,
) -> dict[str, Any]:
    filtros = {"cnpj": cnpj, "razao_social": razao_social, "responsavel": responsavel,
               "tributo": tributo, "data_inicio": data_inicio, "data_fim": data_fim}
    return svc.resumo(db, usuario.organizacao_id, {k: v for k, v in filtros.items() if v})


@router.get("/series")
def series(
    usuario: UsuarioAtual, db: DbSession, dias: int = Query(90, ge=7, le=730)
) -> dict[str, Any]:
    return svc.series_temporais(db, usuario.organizacao_id, dias)
