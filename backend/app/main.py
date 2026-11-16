"""Aplicação FastAPI do Monitor Tributário."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.db import init_db

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("monitor")

DESCRICAO = """
Plataforma de monitoramento tributário: importação de clientes, acompanhamento de
PER/DCOMP, procurações eletrônicas e situação fiscal, com comparação entre
consultas, alertas explicáveis e trilha de auditoria.

**Princípios do sistema**
* transmissão de PER/DCOMP não equivale a homologação;
* procuração constante em planilha não é considerada ativa sem validação por fonte;
* falha de consulta nunca é interpretada como ausência de pendência;
* toda informação carrega origem e data/hora da consulta.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.environment == "prod" and "dev-only-insecure" in settings.secret_key:
        raise RuntimeError("Defina MT_SECRET_KEY antes de rodar em produção.")
    from app.services.agendador import iniciar, parar

    iniciar()
    log.info("Monitor Tributário iniciado (ambiente=%s, banco=%s)",
             settings.environment, settings.database_url.split("://")[0])
    yield
    parar()


app = FastAPI(
    title=settings.app_name,
    description=DESCRICAO,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Cache-Control"] = "no-store"
    if settings.environment == "prod":
        resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resposta


@app.exception_handler(ValueError)
async def erro_valor(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


app.include_router(api_router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["Sistema"])
def health() -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.db import engine

    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        banco = "ok"
    except Exception as exc:  # noqa: BLE001
        banco = f"erro: {exc}"
    return {"status": "ok" if banco == "ok" else "degradado", "banco": banco,
            "ambiente": settings.environment, "versao": app.version}


@app.get(f"{settings.api_prefix}/info", tags=["Sistema"])
def info() -> dict[str, Any]:
    return {
        "aplicacao": settings.app_name,
        "versao": app.version,
        "ambiente": settings.environment,
        "conectores": {
            "procuracao": settings.connector_procuracao,
            "compensacao": settings.connector_compensacao,
            "situacao_fiscal": settings.connector_situacao_fiscal,
        },
        "ia": {"regras": settings.ia_enabled, "llm": settings.ia_llm_enabled},
        "email": settings.email_enabled,
        "agendador": settings.scheduler_enabled,
        "consulta_desatualizada_dias": settings.consulta_desatualizada_dias,
        "alerta_procuracao_dias": settings.alerta_procuracao_dias,
    }


# Serve o frontend compilado, quando existir (deploy em um único container).
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    if (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str) -> FileResponse:
        """Entrega o SPA: arquivos estáticos ou index.html para rotas do React Router."""
        arquivo = (_dist / caminho).resolve()
        if caminho and arquivo.is_file() and str(arquivo).startswith(str(_dist.resolve())):
            return FileResponse(arquivo)
        return FileResponse(_dist / "index.html")
