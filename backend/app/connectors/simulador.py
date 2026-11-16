"""Conector simulador: 'mundo fiscal' fictício para protótipo e testes.

Lê a tabela estado_simulado (dados inventados pelo próprio sistema) e devolve
respostas no mesmo formato de um conector real, incluindo cenários de
indisponibilidade e de ausência de autorização. Assim é possível validar
alertas, comparativos e histórico sem nenhum dado real e sem acessar a
Receita Federal.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import CapacidadeFonte, ResultadoConsulta
from app.models.cliente import Cliente
from app.models.enums import Disponibilidade, OrigemInformacao
from app.models.monitoramento import EstadoSimulado

_CAP_LIMITACOES = [
    "Ambiente de testes: os dados NÃO vêm da Receita Federal.",
    "Deve permanecer desligado em produção (MT_CONNECTOR_*).",
]


def _capacidade(dominio: str) -> CapacidadeFonte:
    return CapacidadeFonte(
        nome=f"Simulador de {dominio} (dados fictícios)",
        origem=OrigemInformacao.SIMULADOR,
        automatizada=True,
        requer_certificado=False,
        requer_procuracao=False,
        poderes_necessarios=[],
        limitacoes=_CAP_LIMITACOES,
        referencia="docs/MANUAL_DE_USO.md#simulador",
    )


class _BaseSimulador:
    dominio = "generico"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.capacidade = _capacidade(self.dominio)

    def _estado(self, cnpj: str) -> EstadoSimulado | None:
        return self.db.scalar(
            select(EstadoSimulado)
            .join(Cliente, Cliente.id == EstadoSimulado.cliente_id)
            .where(Cliente.cnpj == cnpj)
        )

    def _sem_estado(self, cnpj: str) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.SEM_DADOS,
            origem=OrigemInformacao.SIMULADOR,
            fonte_descricao=self.capacidade.nome,
            mensagem=f"Nenhum estado simulado cadastrado para o CNPJ {cnpj}.",
        )

    def _indisponivel(self, motivo: str) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.INDISPONIVEL,
            origem=OrigemInformacao.SIMULADOR,
            fonte_descricao=self.capacidade.nome,
            mensagem=motivo,
        )

    def _nao_autorizado(self, motivo: str) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.NAO_AUTORIZADO,
            origem=OrigemInformacao.SIMULADOR,
            fonte_descricao=self.capacidade.nome,
            mensagem=motivo,
        )

    def _ok(self, dados: Any, mensagem: str | None = None) -> ResultadoConsulta:
        return ResultadoConsulta(
            disponibilidade=Disponibilidade.OK,
            origem=OrigemInformacao.SIMULADOR,
            fonte_descricao=self.capacidade.nome,
            dados=dados,
            mensagem=mensagem,
        )


class SimuladorSituacaoFiscal(_BaseSimulador):
    dominio = "situação fiscal"

    def consultar(self, *, cnpj: str, contexto: Any = None) -> ResultadoConsulta:
        estado = self._estado(cnpj)
        if estado is None:
            return self._sem_estado(cnpj)
        bloco = dict(estado.situacao_fiscal or {})
        falha = bloco.get("forcar")
        if falha == "INDISPONIVEL":
            return self._indisponivel("Serviço de situação fiscal indisponível (simulado).")
        if falha == "NAO_AUTORIZADO":
            return self._nao_autorizado(
                "Procuração sem poderes para consulta de situação fiscal (simulado)."
            )
        return self._ok(
            {
                "situacao_geral": bloco.get("situacao_geral"),
                "pendencias": bloco.get("pendencias", []),
                "relatorio_bruto": bloco.get("relatorio_bruto"),
            }
        )


class SimuladorCompensacao(_BaseSimulador):
    dominio = "PER/DCOMP"

    def consultar(self, *, cnpj: str, numero_perdcomp: str, contexto: Any = None) -> ResultadoConsulta:
        estado = self._estado(cnpj)
        if estado is None:
            return self._sem_estado(cnpj)
        mapa = dict(estado.compensacoes or {})
        if mapa.get("forcar") == "INDISPONIVEL":
            return self._indisponivel("Consulta PER/DCOMP indisponível (simulado).")
        registro = mapa.get(numero_perdcomp)
        if registro is None:
            return ResultadoConsulta(
                disponibilidade=Disponibilidade.SEM_DADOS,
                origem=OrigemInformacao.SIMULADOR,
                fonte_descricao=self.capacidade.nome,
                mensagem=f"PER/DCOMP {numero_perdcomp} não localizada na fonte simulada.",
            )
        return self._ok(registro)


class SimuladorProcuracao(_BaseSimulador):
    dominio = "procurações eletrônicas"

    def consultar(self, *, cnpj: str, numero: str | None = None, contexto: Any = None) -> ResultadoConsulta:
        estado = self._estado(cnpj)
        if estado is None:
            return self._sem_estado(cnpj)
        mapa = dict(estado.procuracoes or {})
        if mapa.get("forcar") == "INDISPONIVEL":
            return self._indisponivel("Consulta de procurações indisponível (simulado).")
        if numero is None:
            registros = [v for k, v in mapa.items() if k != "forcar"]
            return self._ok(registros)
        registro = mapa.get(numero)
        if registro is None:
            return ResultadoConsulta(
                disponibilidade=Disponibilidade.SEM_DADOS,
                origem=OrigemInformacao.SIMULADOR,
                fonte_descricao=self.capacidade.nome,
                mensagem=f"Procuração {numero} não localizada na fonte simulada.",
            )
        return self._ok(registro)
