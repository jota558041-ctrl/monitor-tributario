"""Seleção dos conectores ativos conforme configuração."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.connectors.base import CapacidadeFonte
from app.connectors.integra_contador import (
    IntegraCompensacao,
    IntegraProcuracao,
    IntegraSituacaoFiscal,
)
from app.connectors.manual import ConectorManual
from app.connectors.simulador import (
    SimuladorCompensacao,
    SimuladorProcuracao,
    SimuladorSituacaoFiscal,
)
from app.core.config import settings

_MAPA = {
    "procuracao": {
        "manual": lambda db: ConectorManual("procurações"),
        "simulador": SimuladorProcuracao,
        "integra_contador": IntegraProcuracao,
    },
    "compensacao": {
        "manual": lambda db: ConectorManual("PER/DCOMP"),
        "simulador": SimuladorCompensacao,
        "integra_contador": IntegraCompensacao,
    },
    "situacao_fiscal": {
        "manual": lambda db: ConectorManual("situação fiscal"),
        "simulador": SimuladorSituacaoFiscal,
        "integra_contador": IntegraSituacaoFiscal,
    },
}


def _escolhido(dominio: str) -> str:
    return getattr(settings, f"connector_{dominio}")


def obter_conector(dominio: str, db: Session) -> Any:
    escolha = _escolhido(dominio)
    fabrica = _MAPA[dominio][escolha]
    return fabrica(db)


def conector_procuracao(db: Session) -> Any:
    return obter_conector("procuracao", db)


def conector_compensacao(db: Session) -> Any:
    return obter_conector("compensacao", db)


def conector_situacao_fiscal(db: Session) -> Any:
    return obter_conector("situacao_fiscal", db)


def capacidades(db: Session) -> list[dict[str, Any]]:
    """Relatório de capacidades/limitações das fontes ativas (exposto na API)."""
    saida: list[dict[str, Any]] = []
    for dominio in ("procuracao", "compensacao", "situacao_fiscal"):
        conector = obter_conector(dominio, db)
        cap: CapacidadeFonte = conector.capacidade
        saida.append(
            {
                "dominio": dominio,
                "conector_configurado": _escolhido(dominio),
                "nome": cap.nome,
                "origem": cap.origem.value,
                "automatizada": cap.automatizada,
                "requer_certificado": cap.requer_certificado,
                "requer_procuracao": cap.requer_procuracao,
                "poderes_necessarios": cap.poderes_necessarios,
                "limitacoes": cap.limitacoes,
                "referencia": cap.referencia,
            }
        )
    return saida
