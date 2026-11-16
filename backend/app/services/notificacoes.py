"""Notificações: registro no sistema e envio por e-mail (preparado)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.models.alerta import Alerta, Notificacao
from app.models.enums import CanalNotificacao, StatusNotificacao


def criar_notificacoes(
    db: Session, alerta: Alerta, *, canais: list[str] | None = None,
    destinatarios: list[str] | None = None,
) -> list[Notificacao]:
    canais = canais or [CanalNotificacao.SISTEMA]
    criadas: list[Notificacao] = []
    for canal in canais:
        alvos = destinatarios if canal == CanalNotificacao.EMAIL else [None]
        for alvo in alvos or [None]:
            status = StatusNotificacao.PENDENTE
            if canal == CanalNotificacao.SISTEMA:
                status = StatusNotificacao.ENVIADA
            elif canal == CanalNotificacao.EMAIL and not settings.email_enabled:
                status = StatusNotificacao.DESABILITADO
            notificacao = Notificacao(
                alerta_id=alerta.id,
                organizacao_id=alerta.organizacao_id,
                canal=str(canal),
                destinatario=alvo,
                status=str(status),
                assunto=f"[{alerta.criticidade}] {alerta.titulo}",
                corpo=montar_corpo(alerta),
                enviada_em=utcnow() if status == StatusNotificacao.ENVIADA else None,
                created_at=utcnow(),
            )
            db.add(notificacao)
            criadas.append(notificacao)
    db.flush()
    return criadas


def montar_corpo(alerta: Alerta) -> str:
    linhas = [
        alerta.mensagem,
        "",
        f"Criticidade: {alerta.criticidade}",
        f"Tipo: {alerta.tipo}",
        f"Gerado em: {alerta.gerado_em.strftime('%d/%m/%Y %H:%M')} (UTC)",
    ]
    if alerta.explicacao:
        linhas += ["", "Por que este alerta foi gerado:", alerta.explicacao]
    if alerta.evidencias:
        linhas += ["", "Evidências:"]
        for ev in alerta.evidencias[:6]:
            partes = [f"{k}={v}" for k, v in ev.items() if k in
                      ("fonte", "consultado_em", "campo", "de", "para", "disponibilidade")]
            linhas.append("  - " + "; ".join(partes))
    linhas += ["", "Monitor Tributário - mensagem automática. Confira no painel antes de agir."]
    return "\n".join(linhas)


def enviar_pendentes(db: Session, organizacao_id: str | None = None, limite: int = 50) -> dict[str, Any]:
    """Envia as notificações de e-mail pendentes (se o SMTP estiver habilitado)."""
    consulta = select(Notificacao).where(
        Notificacao.status == StatusNotificacao.PENDENTE,
        Notificacao.canal == CanalNotificacao.EMAIL,
    )
    if organizacao_id:
        consulta = consulta.where(Notificacao.organizacao_id == organizacao_id)
    pendentes = db.scalars(consulta.limit(limite)).all()
    if not settings.email_enabled:
        for n in pendentes:
            n.status = str(StatusNotificacao.DESABILITADO)
            n.erro = "Envio de e-mail desabilitado (MT_EMAIL_ENABLED=false)."
        db.flush()
        return {"enviadas": 0, "desabilitadas": len(pendentes)}

    enviadas = erros = 0
    try:
        servidor = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_tls:
            servidor.starttls()
        if settings.smtp_user:
            servidor.login(settings.smtp_user, settings.smtp_password)
    except Exception as exc:  # noqa: BLE001
        for n in pendentes:
            n.erro = f"Falha de conexão SMTP: {exc}"
            n.status = str(StatusNotificacao.ERRO)
        db.flush()
        return {"enviadas": 0, "erros": len(pendentes), "detalhe": str(exc)}

    with servidor:
        for n in pendentes:
            try:
                msg = EmailMessage()
                msg["Subject"] = n.assunto or "Monitor Tributário"
                msg["From"] = settings.smtp_from
                msg["To"] = n.destinatario or settings.smtp_from
                msg.set_content(n.corpo or "")
                servidor.send_message(msg)
                n.status = str(StatusNotificacao.ENVIADA)
                n.enviada_em = utcnow()
                enviadas += 1
            except Exception as exc:  # noqa: BLE001
                n.status = str(StatusNotificacao.ERRO)
                n.erro = str(exc)
                erros += 1
    db.flush()
    return {"enviadas": enviadas, "erros": erros}
