"""Status e capacidades das fontes de informação (transparência de origem)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession, UsuarioAtual
from app.connectors.integra_contador import IntegraContadorClient
from app.connectors.registry import capacidades
from app.core.config import settings

router = APIRouter(prefix="/integracoes", tags=["Integrações"])


@router.get("/status")
def status_integracoes(_: UsuarioAtual, db: DbSession) -> dict[str, Any]:
    cliente = IntegraContadorClient()
    return {
        "fontes": capacidades(db),
        "integra_contador": {
            "habilitado": settings.integra_contador_enabled,
            "configurado": cliente.configurado,
            "motivo": None if cliente.configurado else cliente.motivo_indisponibilidade(),
            "rate_limit_rpm": settings.integra_contador_rate_limit_rpm,
        },
        "regras_de_ouro": [
            "Nenhum endpoint é inventado: URLs e identificadores de serviço vêm de configuração.",
            "Não há contorno de CAPTCHA, MFA ou qualquer controle de segurança.",
            "Sem API oficial disponível, usa-se importação manual com registro de origem e data.",
            "Falha de consulta nunca é tratada como ausência de pendência.",
        ],
        "documentacao": "docs/INTEGRACAO_RECEITA_FEDERAL.md",
    }
