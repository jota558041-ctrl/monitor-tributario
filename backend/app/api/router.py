"""Agregador de rotas da API."""
from fastapi import APIRouter

from app.api import (
    alertas,
    auditoria,
    auth,
    clientes,
    compensacoes,
    dashboard,
    fiscal,
    ia,
    importacoes,
    integracoes,
    monitoramento,
    procuracoes,
)

api_router = APIRouter()
for modulo in (auth, clientes, importacoes, procuracoes, compensacoes, fiscal,
               alertas, dashboard, monitoramento, ia, auditoria, integracoes):
    api_router.include_router(modulo.router)
