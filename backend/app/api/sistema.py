"""Prontidão para produção: checagens objetivas do ambiente."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, exige_perfil
from app.core.config import settings
from app.models.enums import Perfil
from app.models.integracao import AmostraIntegracao
from app.models.tenant import Usuario

router = APIRouter(prefix="/sistema", tags=["Sistema"])

SomenteAdministrador = Annotated[Usuario, Depends(exige_perfil(Perfil.ADMIN))]

SENHAS_DEMONSTRACAO = {
    "admin@monitortributario.com.br", "analista@monitortributario.com.br",
    "auditor@monitortributario.com.br",
}


def _item(nome: str, ok: bool, detalhe: str, recomendacao: str = "",
          critico: bool = True) -> dict[str, Any]:
    return {"item": nome, "situacao": "OK" if ok else ("CRITICO" if critico else "ATENCAO"),
            "detalhe": detalhe, "recomendacao": "" if ok else recomendacao}


@router.get("/prontidao")
def prontidao(usuario: SomenteAdministrador, db: DbSession) -> dict[str, Any]:
    """Checklist automatizado antes de colocar o sistema em produção."""
    itens: list[dict[str, Any]] = []
    producao = settings.environment == "prod"

    itens.append(_item(
        "Ambiente", producao, f"MT_ENVIRONMENT = {settings.environment}",
        "Defina MT_ENVIRONMENT=prod no ambiente produtivo.", critico=False))
    itens.append(_item(
        "Modo debug", not settings.debug, f"MT_DEBUG = {settings.debug}",
        "Desligue MT_DEBUG em produção.", critico=producao))
    itens.append(_item(
        "Chave de assinatura (JWT)", "dev-only-insecure" not in settings.secret_key,
        "MT_SECRET_KEY personalizada" if "dev-only-insecure" not in settings.secret_key
        else "usando a chave padrão de desenvolvimento",
        "Gere com: python -c \"import secrets; print(secrets.token_urlsafe(48))\""))
    itens.append(_item(
        "Chave de criptografia em repouso", bool(settings.fernet_key),
        "MT_FERNET_KEY definida" if settings.fernet_key
        else "derivada da MT_SECRET_KEY (aceitável só fora de produção)",
        "Gere com: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""))
    itens.append(_item(
        "Banco de dados", not settings.is_sqlite,
        settings.database_url.split("://")[0],
        "Use PostgreSQL em produção; SQLite é para desenvolvimento.", critico=producao))

    fontes = {settings.connector_procuracao, settings.connector_compensacao,
              settings.connector_situacao_fiscal}
    itens.append(_item(
        "Fontes de dados", "simulador" not in fontes,
        f"procuração={settings.connector_procuracao}, "
        f"PER/DCOMP={settings.connector_compensacao}, "
        f"situação fiscal={settings.connector_situacao_fiscal}",
        "Em produção use 'manual' ou 'integra_contador'; o simulador gera dados fictícios."))
    itens.append(_item(
        "Modo homologação da integração", not settings.integra_contador_modo_homologacao,
        f"MT_INTEGRA_CONTADOR_MODO_HOMOLOGACAO = {settings.integra_contador_modo_homologacao}",
        "Desligue após concluir o mapeamento: ele grava respostas brutas com dados fiscais.",
        critico=False))

    origens_abertas = [o for o in settings.cors_origins if "localhost" in o or "127.0.0.1" in o]
    itens.append(_item(
        "CORS", not (producao and origens_abertas),
        f"{len(settings.cors_origins)} origem(ns): {', '.join(settings.cors_origins) or 'nenhuma'}",
        "Restrinja MT_CORS_ORIGINS ao domínio real da aplicação.", critico=False))

    usuarios_demo = db.scalars(
        select(Usuario).where(Usuario.organizacao_id == usuario.organizacao_id,
                              Usuario.email.in_(SENHAS_DEMONSTRACAO), Usuario.ativo.is_(True))
    ).all()
    itens.append(_item(
        "Usuários de demonstração", not usuarios_demo,
        f"{len(usuarios_demo)} usuário(s) de demonstração ativo(s)"
        if usuarios_demo else "nenhum usuário de demonstração ativo",
        "Troque as senhas ou desative os usuários de demonstração antes de liberar o acesso."))

    administradores = db.scalar(
        select(func.count()).select_from(Usuario).where(
            Usuario.organizacao_id == usuario.organizacao_id,
            Usuario.perfil == Perfil.ADMIN, Usuario.ativo.is_(True))
    ) or 0
    itens.append(_item(
        "Administradores ativos", 1 <= administradores <= 3,
        f"{administradores} administrador(es) ativo(s)",
        "Mantenha o número de administradores no mínimo necessário.", critico=False))

    itens.append(_item(
        "Proteção contra força bruta", settings.login_max_tentativas > 0,
        f"bloqueio após {settings.login_max_tentativas} falhas por "
        f"{settings.login_bloqueio_minutos} minuto(s)", "", critico=False))
    itens.append(_item(
        "Agendador de monitoramento", settings.scheduler_enabled,
        "ativo" if settings.scheduler_enabled else "desligado",
        "Ative MT_SCHEDULER_ENABLED em uma única instância do backend.", critico=False))
    itens.append(_item(
        "Notificação por e-mail", settings.email_enabled,
        "SMTP configurado" if settings.email_enabled else "desligado (alertas só no sistema)",
        "Configure MT_SMTP_* e MT_EMAIL_ENABLED para avisar a equipe fora do sistema.",
        critico=False))
    itens.append(_item(
        "Retenção de dados",
        settings.retencao_consultas_dias >= 1825 and settings.retencao_auditoria_dias >= 1825,
        f"consultas: {settings.retencao_consultas_dias} dias, "
        f"auditoria: {settings.retencao_auditoria_dias} dias",
        "Guarde ao menos 5 anos para acompanhar o prazo fiscal.", critico=False))

    criticos = [i for i in itens if i["situacao"] == "CRITICO"]
    atencao = [i for i in itens if i["situacao"] == "ATENCAO"]
    return {
        "pronto_para_producao": not criticos,
        "resumo": {"ok": len(itens) - len(criticos) - len(atencao),
                   "atencao": len(atencao), "critico": len(criticos), "total": len(itens)},
        "itens": itens,
        "verificado_em": datetime.now(UTC).isoformat(),
        "observacao": "A verificação cobre a configuração da aplicação. Backup, TLS, firewall "
                      "e isolamento de rede dependem da infraestrutura e devem ser conferidos "
                      "separadamente (ver docs/INSTALACAO.md).",
    }


@router.get("/amostras-integracao")
def amostras(
    usuario: SomenteAdministrador, db: DbSession, limite: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    """Amostras capturadas em modo homologação, para mapear os campos do contrato."""
    registros = list(db.scalars(
        select(AmostraIntegracao).order_by(AmostraIntegracao.created_at.desc()).limit(limite)
    ))
    return {
        "modo_homologacao_ativo": settings.integra_contador_modo_homologacao,
        "total": len(registros),
        "aviso": "As amostras podem conter dados fiscais completos do contribuinte. "
                 "Use apenas durante o mapeamento e apague em seguida.",
        "itens": [
            {"id": a.id, "dominio": a.dominio, "provedor": a.provedor,
             "contribuinte": a.contribuinte, "id_sistema": a.id_sistema,
             "id_servico": a.id_servico, "http_status": a.http_status,
             "disponibilidade": a.disponibilidade, "duracao_ms": a.duracao_ms,
             "erro": a.erro, "requisicao": a.requisicao, "resposta": a.resposta,
             "created_at": a.created_at.isoformat()}
            for a in registros
        ],
    }


@router.delete("/amostras-integracao", status_code=200)
def limpar_amostras(
    usuario: SomenteAdministrador, db: DbSession, dias: int = Query(0, ge=0, le=365)
) -> dict[str, int]:
    """Apaga amostras com mais de `dias` (0 = todas)."""
    consulta = select(AmostraIntegracao)
    if dias:
        consulta = consulta.where(
            AmostraIntegracao.created_at < datetime.now(UTC) - timedelta(days=dias))
    registros = list(db.scalars(consulta))
    for registro in registros:
        db.delete(registro)
    db.commit()
    return {"removidas": len(registros)}
