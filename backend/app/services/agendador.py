"""Agendador de monitoramento (APScheduler) alimentado pelas regras do banco."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.alerta import RegraMonitoramento
from app.models.tenant import Organizacao

log = logging.getLogger("monitor.agendador")
_scheduler: BackgroundScheduler | None = None


def _executar_regra(regra_id: str) -> None:
    from app.services.monitoramento import executar
    from app.services.notificacoes import enviar_pendentes

    db = SessionLocal()
    try:
        regra = db.get(RegraMonitoramento, regra_id)
        if regra is None or not regra.ativo:
            return
        execucao = executar(
            db, organizacao_id=regra.organizacao_id, tipo=regra.tipo_monitoramento,
            clientes_ids=regra.clientes_escopo or None, acionada_por="AGENDADOR",
            regra=regra,
        )
        if "EMAIL" in (regra.canais or []):
            enviar_pendentes(db, regra.organizacao_id)
        db.commit()
        log.info("Regra %s executada: %s alertas", regra.nome, execucao.alertas_gerados)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Falha ao executar regra %s", regra_id)
    finally:
        db.close()


def _executar_padrao(organizacao_id: str) -> None:
    from app.services.monitoramento import executar

    db = SessionLocal()
    try:
        executar(db, organizacao_id=organizacao_id, acionada_por="AGENDADOR_PADRAO")
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Falha no monitoramento padrão da organização %s", organizacao_id)
    finally:
        db.close()


def iniciar() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.scheduler_enabled:
        log.info("Agendador desabilitado (MT_SCHEDULER_ENABLED=false).")
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    _scheduler.start()
    recarregar()
    return _scheduler


def parar() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def recarregar() -> dict[str, Any]:
    """Relê as regras do banco e reprograma os jobs."""
    if _scheduler is None:
        return {"ativo": False, "jobs": []}
    for job in _scheduler.get_jobs():
        job.remove()

    db = SessionLocal()
    try:
        regras = list(db.scalars(
            select(RegraMonitoramento).where(RegraMonitoramento.ativo.is_(True))
        ))
        for regra in regras:
            try:
                gatilho = CronTrigger.from_crontab(regra.cron, timezone=settings.scheduler_timezone)
            except ValueError:
                log.warning("Cron inválido na regra %s: %s", regra.nome, regra.cron)
                continue
            _scheduler.add_job(
                _executar_regra, gatilho, args=[regra.id], id=f"regra:{regra.id}",
                name=regra.nome, replace_existing=True, max_instances=1, coalesce=True,
            )
            regra.proxima_execucao = gatilho.get_next_fire_time(None, datetime.now())
        if not regras:
            for org in db.scalars(select(Organizacao).where(Organizacao.ativo.is_(True))):
                _scheduler.add_job(
                    _executar_padrao,
                    CronTrigger.from_crontab(settings.monitoramento_cron,
                                             timezone=settings.scheduler_timezone),
                    args=[org.id], id=f"padrao:{org.id}", name=f"Monitoramento padrão {org.nome}",
                    replace_existing=True, max_instances=1, coalesce=True,
                )
        db.commit()
    finally:
        db.close()
    return status_agendador()


def status_agendador() -> dict[str, Any]:
    if _scheduler is None:
        return {"ativo": False, "timezone": settings.scheduler_timezone, "jobs": [],
                "motivo": "Agendador não iniciado ou desabilitado."}
    return {
        "ativo": True,
        "timezone": settings.scheduler_timezone,
        "jobs": [
            {"id": j.id, "nome": j.name,
             "proxima_execucao": j.next_run_time.isoformat() if j.next_run_time else None,
             "gatilho": str(j.trigger)}
            for j in _scheduler.get_jobs()
        ],
    }
