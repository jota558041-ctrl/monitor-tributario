"""Conector 'manual': nenhuma consulta automática é feita.

Usado quando não existe API oficial ou automação autorizada para o serviço.
O sistema continua funcionando: o resultado oficial é importado manualmente
(upload de relatório / preenchimento) e fica marcado como NÃO consultado
automaticamente, com a data informada pelo usuário.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import CapacidadeFonte, ResultadoConsulta
from app.models.enums import Disponibilidade, OrigemInformacao

_LIMITACOES = [
    "Não há consulta automática configurada para este serviço.",
    "O resultado precisa ser importado manualmente a partir do e-CAC/PER-DCOMP Web.",
    "Enquanto não houver importação, a informação permanece NAO_CONSULTADO.",
]


class ConectorManual:
    def __init__(self, dominio: str) -> None:
        self.dominio = dominio
        self.capacidade = CapacidadeFonte(
            nome=f"Importação manual ({dominio})",
            origem=OrigemInformacao.MANUAL,
            automatizada=False,
            requer_certificado=False,
            requer_procuracao=False,
            poderes_necessarios=[],
            limitacoes=_LIMITACOES,
            referencia="docs/INTEGRACAO_RECEITA_FEDERAL.md",
        )

    def _resposta(self) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.NAO_CONSULTADO,
            origem=OrigemInformacao.MANUAL,
            fonte_descricao=self.capacidade.nome,
            mensagem=(
                "Consulta automática não configurada para este domínio. "
                "Importe o resultado oficial manualmente."
            ),
        )

    def consultar(self, **_: Any) -> ResultadoConsulta:
        return self._resposta()
