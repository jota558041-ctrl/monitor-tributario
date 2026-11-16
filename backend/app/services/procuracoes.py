"""Procurações eletrônicas: situação, semáforo e registro de consultas.

Regra inviolável: a presença de uma procuração na planilha NÃO significa que
ela esteja ativa. Enquanto não houver validação por fonte autorizada, a
situação do sistema é DESCONHECIDA e o semáforo é CINZA. O que vem da planilha
fica guardado em `situacao_declarada`, separadamente.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ResultadoConsulta
from app.core.crypto import content_hash
from app.core.serial import para_json
from app.models.cliente import Cliente
from app.models.enums import (
    FONTES_AUTORIZADAS,
    Disponibilidade,
    OrigemInformacao,
    Semaforo,
    SituacaoProcuracao,
)
from app.models.procuracao import Procuracao, ProcuracaoConsulta
from app.services.parsers import parse_data, texto_ou_none

LIMITE_ALERTA_DIAS = 30


def situacao_por_data(data_fim: date | None, hoje: date | None = None) -> SituacaoProcuracao:
    hoje = hoje or date.today()
    if data_fim is None:
        return SituacaoProcuracao.DESCONHECIDA
    if data_fim < hoje:
        return SituacaoProcuracao.EXPIRADA
    if (data_fim - hoje).days <= LIMITE_ALERTA_DIAS:
        return SituacaoProcuracao.PROXIMA_VENCIMENTO
    return SituacaoProcuracao.ATIVA


def semaforo(procuracao: Procuracao, hoje: date | None = None) -> Semaforo:
    if not procuracao.validada_por_fonte or procuracao.disponibilidade != Disponibilidade.OK:
        return Semaforo.CINZA
    situacao = procuracao.situacao
    if situacao in (SituacaoProcuracao.EXPIRADA, SituacaoProcuracao.REVOGADA):
        return Semaforo.VERMELHO
    if situacao == SituacaoProcuracao.PROXIMA_VENCIMENTO:
        return Semaforo.AMARELO
    if situacao == SituacaoProcuracao.ATIVA:
        return Semaforo.VERDE
    return Semaforo.CINZA


def dias_para_vencer(procuracao: Procuracao, hoje: date | None = None) -> int | None:
    if procuracao.data_fim is None:
        return None
    return (procuracao.data_fim - (hoje or date.today())).days


def upsert_procuracao(
    db: Session, cliente: Cliente, dados: dict[str, Any],
    *, origem: str = OrigemInformacao.PLANILHA,
) -> tuple[Procuracao, bool]:
    """Cria/atualiza procuração. Chave: número, ou (cliente + data de validade)."""
    numero = texto_ou_none(dados.get("numero"))
    data_fim = parse_data(dados.get("data_fim"))
    consulta = select(Procuracao).where(Procuracao.cliente_id == cliente.id)
    if numero:
        existente = db.scalar(consulta.where(Procuracao.numero == numero))
    elif data_fim:
        existente = db.scalar(consulta.where(Procuracao.data_fim == data_fim))
    else:
        existente = None

    criada = existente is None
    proc = existente or Procuracao(
        organizacao_id=cliente.organizacao_id,
        cliente_id=cliente.id,
        outorgante_cnpj=cliente.cnpj,
        origem_informacao=str(origem),
        disponibilidade=Disponibilidade.NAO_CONSULTADO,
    )
    if numero:
        proc.numero = numero
    if data_fim:
        proc.data_fim = data_fim
    inicio = parse_data(dados.get("data_inicio"))
    if inicio:
        proc.data_inicio = inicio
    for campo in ("procurador_doc", "procurador_nome", "observacoes"):
        valor = texto_ou_none(dados.get(campo))
        if valor:
            setattr(proc, campo, valor)
    if dados.get("poderes"):
        proc.poderes = dados["poderes"]
    if dados.get("servicos_autorizados"):
        proc.servicos_autorizados = dados["servicos_autorizados"]

    # Situação declarada (planilha) x situação do sistema (exige validação)
    proc.situacao_declarada = situacao_por_data(proc.data_fim)
    if not proc.validada_por_fonte:
        proc.situacao = SituacaoProcuracao.DESCONHECIDA
    if criada:
        db.add(proc)
    db.flush()
    return proc, criada


def registrar_consulta(
    db: Session, procuracao: Procuracao, resultado: ResultadoConsulta,
    *, usuario_email: str | None = None,
) -> dict[str, Any]:
    """Aplica o resultado de uma consulta e devolve o que mudou."""
    situacao_anterior = procuracao.situacao
    data_fim_anterior = procuracao.data_fim
    situacao_retornada: str | None = None
    data_fim_retornada: date | None = None

    dados = resultado.dados if isinstance(resultado.dados, dict) else None
    if resultado.disponibilidade == Disponibilidade.OK and dados:
        situacao_retornada = texto_ou_none(dados.get("situacao"))
        data_fim_retornada = parse_data(dados.get("data_fim"))
        if data_fim_retornada:
            procuracao.data_fim = data_fim_retornada
        if parse_data(dados.get("data_inicio")):
            procuracao.data_inicio = parse_data(dados.get("data_inicio"))
        if dados.get("poderes"):
            procuracao.poderes = dados["poderes"]
        if dados.get("servicos_autorizados"):
            procuracao.servicos_autorizados = dados["servicos_autorizados"]
        if situacao_retornada == SituacaoProcuracao.REVOGADA:
            procuracao.situacao = SituacaoProcuracao.REVOGADA
        elif situacao_retornada in set(SituacaoProcuracao):
            procuracao.situacao = situacao_por_data(procuracao.data_fim)
            if situacao_retornada == SituacaoProcuracao.EXPIRADA:
                procuracao.situacao = SituacaoProcuracao.EXPIRADA
        else:
            procuracao.situacao = situacao_por_data(procuracao.data_fim)
        procuracao.validada_por_fonte = resultado.origem in FONTES_AUTORIZADAS
        procuracao.origem_informacao = str(resultado.origem)
    elif resultado.disponibilidade in (Disponibilidade.INDISPONIVEL, Disponibilidade.NAO_AUTORIZADO,
                                       Disponibilidade.SEM_DADOS, Disponibilidade.NAO_CONSULTADO):
        # Falha de consulta não altera a situação conhecida; apenas marca o estado.
        if resultado.disponibilidade != Disponibilidade.SEM_DADOS:
            procuracao.validada_por_fonte = False
            procuracao.situacao = SituacaoProcuracao.DESCONHECIDA

    procuracao.disponibilidade = str(resultado.disponibilidade)
    procuracao.consultado_em = resultado.consultado_em

    db.add(
        ProcuracaoConsulta(
            procuracao_id=procuracao.id,
            origem=str(resultado.origem),
            disponibilidade=str(resultado.disponibilidade),
            situacao_retornada=situacao_retornada,
            data_fim_retornada=data_fim_retornada,
            mensagem=resultado.mensagem,
            payload=para_json(dados),
            hash_conteudo=content_hash(dados) if dados else None,
            consultado_em=resultado.consultado_em,
            criado_por=usuario_email,
        )
    )
    cliente = db.get(Cliente, procuracao.cliente_id)
    if cliente:
        cliente.ultima_consulta_procuracao = resultado.consultado_em
    db.flush()
    return {
        "procuracao_id": procuracao.id,
        "situacao_anterior": situacao_anterior,
        "situacao_nova": procuracao.situacao,
        "mudou_situacao": situacao_anterior != procuracao.situacao,
        "data_fim_anterior": data_fim_anterior.isoformat() if data_fim_anterior else None,
        "data_fim_nova": procuracao.data_fim.isoformat() if procuracao.data_fim else None,
        "disponibilidade": procuracao.disponibilidade,
        "evidencia": resultado.para_evidencia(
            entidade="PROCURACAO", entidade_id=procuracao.id,
            numero=procuracao.numero,
        ),
    }
