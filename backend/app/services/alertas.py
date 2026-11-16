"""Persistência de alertas a partir dos achados, com deduplicação."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.serial import para_json
from app.ia.achados import Achado
from app.models.alerta import Alerta, RegraMonitoramento
from app.models.enums import (
    ORDEM_CRITICIDADE,
    CanalNotificacao,
    Criticidade,
    StatusAlerta,
)
from app.services.notificacoes import criar_notificacoes


def registrar_achados(
    db: Session, organizacao_id: str, achados: list[Achado],
    *, regra: RegraMonitoramento | None = None,
) -> dict[str, Any]:
    """Cria alertas novos; reabre alertas reincidentes; nunca duplica.

    A deduplicação usa `dedup_key`, que inclui o estado observado. Uma mudança
    de estado gera nova chave e, portanto, novo alerta.
    """
    criticidade_minima = Criticidade(regra.criticidade_minima) if regra else Criticidade.INFO
    canais = list(regra.canais) if regra and regra.canais else [CanalNotificacao.SISTEMA]
    destinatarios = list(regra.destinatarios) if regra and regra.destinatarios else []

    criados: list[Alerta] = []
    reabertos: list[Alerta] = []
    ignorados_por_criticidade = 0
    repetidos = 0

    for achado in achados:
        if ORDEM_CRITICIDADE[Criticidade(achado.criticidade)] < ORDEM_CRITICIDADE[criticidade_minima]:
            ignorados_por_criticidade += 1
            continue
        existente = db.scalar(
            select(Alerta).where(
                Alerta.organizacao_id == organizacao_id,
                Alerta.dedup_key == achado.dedup_key,
            )
        )
        if existente is not None:
            if existente.status in (StatusAlerta.RESOLVIDO, StatusAlerta.IGNORADO):
                existente.status = str(StatusAlerta.NOVO)
                existente.gerado_em = utcnow()
                existente.resolvido_em = None
                existente.resolvido_por = None
                existente.evidencias = para_json(achado.evidencias)
                existente.mensagem = achado.mensagem
                existente.explicacao = achado.explicacao
                reabertos.append(existente)
                criar_notificacoes(db, existente, canais=canais, destinatarios=destinatarios)
            else:
                repetidos += 1
                existente.evidencias = para_json(achado.evidencias)
            continue

        alerta = Alerta(
            organizacao_id=organizacao_id,
            cliente_id=achado.cliente_id,
            tipo=str(achado.tipo),
            criticidade=str(achado.criticidade),
            titulo=achado.titulo,
            mensagem=achado.mensagem,
            explicacao=achado.explicacao,
            evidencias=para_json(achado.evidencias),
            entidade=achado.entidade,
            entidade_id=achado.entidade_id,
            regra_id=regra.id if regra else None,
            dedup_key=achado.dedup_key,
            status=str(StatusAlerta.NOVO),
            gerado_em=utcnow(),
        )
        db.add(alerta)
        db.flush()
        criar_notificacoes(db, alerta, canais=canais, destinatarios=destinatarios)
        criados.append(alerta)

    db.flush()
    return {
        "criados": len(criados),
        "reabertos": len(reabertos),
        "repetidos": repetidos,
        "ignorados_por_criticidade": ignorados_por_criticidade,
        "ids": [a.id for a in criados],
    }


def resolver(
    db: Session, alerta: Alerta, *, usuario_email: str, status: StatusAlerta = StatusAlerta.RESOLVIDO,
    nota: str | None = None,
) -> Alerta:
    alerta.status = str(status)
    alerta.resolvido_em = utcnow()
    alerta.resolvido_por = usuario_email
    alerta.nota_resolucao = nota
    db.flush()
    return alerta
