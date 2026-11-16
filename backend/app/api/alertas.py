"""Alertas, regras de monitoramento e notificações."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession, PodeEscrever, SomenteAdmin, UsuarioAtual
from app.core.auditoria import registrar
from app.models.alerta import Alerta, Notificacao, RegraMonitoramento
from app.models.cliente import Cliente
from app.models.enums import Criticidade, StatusAlerta
from app.schemas.comum import Pagina
from app.schemas.dominio import (
    AlertaAcaoIn,
    AlertaOut,
    NotificacaoOut,
    RegraIn,
    RegraOut,
)
from app.services import alertas as svc
from app.services.cnpj import formatar_cnpj
from app.services.notificacoes import enviar_pendentes

router = APIRouter(tags=["Alertas"])


def _saida(alerta: Alerta, cliente: Cliente | None) -> AlertaOut:
    out = AlertaOut.model_validate(alerta)
    if cliente:
        out.cliente_razao_social = cliente.razao_social
        out.cliente_cnpj = formatar_cnpj(cliente.cnpj)
    return out


@router.get("/alertas", response_model=Pagina[AlertaOut])
def listar(
    usuario: UsuarioAtual, db: DbSession,
    status_alerta: StatusAlerta | None = Query(default=None, alias="status"),
    criticidade: Criticidade | None = None, tipo: str | None = None,
    cliente_id: str | None = None, responsavel: str | None = None,
    pagina: int = Query(1, ge=1), tamanho: int = Query(50, ge=1, le=500),
) -> Pagina[AlertaOut]:
    consulta = (
        select(Alerta, Cliente)
        .outerjoin(Cliente, Cliente.id == Alerta.cliente_id)
        .where(Alerta.organizacao_id == usuario.organizacao_id)
    )
    if status_alerta:
        consulta = consulta.where(Alerta.status == status_alerta)
    if criticidade:
        consulta = consulta.where(Alerta.criticidade == criticidade)
    if tipo:
        consulta = consulta.where(Alerta.tipo == tipo)
    if cliente_id:
        consulta = consulta.where(Alerta.cliente_id == cliente_id)
    if responsavel:
        consulta = consulta.where(Cliente.responsavel == responsavel)

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    linhas = list(db.execute(
        consulta.order_by(Alerta.gerado_em.desc()).offset((pagina - 1) * tamanho).limit(tamanho)
    ))
    return Pagina(itens=[_saida(a, c) for a, c in linhas], total=total,
                  pagina=pagina, tamanho=tamanho)


@router.get("/alertas/tipos")
def tipos(usuario: UsuarioAtual, db: DbSession) -> list[dict[str, Any]]:
    linhas = db.execute(
        select(Alerta.tipo, Alerta.criticidade, func.count())
        .where(Alerta.organizacao_id == usuario.organizacao_id)
        .group_by(Alerta.tipo, Alerta.criticidade)
    ).all()
    return [{"tipo": t, "criticidade": c, "quantidade": q} for t, c, q in linhas]


@router.get("/alertas/{alerta_id}", response_model=AlertaOut)
def detalhar(alerta_id: str, usuario: UsuarioAtual, db: DbSession) -> AlertaOut:
    alerta = db.get(Alerta, alerta_id)
    if alerta is None or alerta.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta não encontrado.")
    return _saida(alerta, db.get(Cliente, alerta.cliente_id) if alerta.cliente_id else None)


@router.post("/alertas/{alerta_id}/acao", response_model=AlertaOut)
def agir(
    alerta_id: str, dados: AlertaAcaoIn, usuario: PodeEscrever, db: DbSession
) -> AlertaOut:
    alerta = db.get(Alerta, alerta_id)
    if alerta is None or alerta.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta não encontrado.")
    svc.resolver(db, alerta, usuario_email=usuario.email, status=dados.status, nota=dados.nota)
    registrar(db, acao="ALERTA_ACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="ALERTA", entidade_id=alerta.id,
              detalhe={"status": str(dados.status), "nota": dados.nota})
    db.commit()
    db.refresh(alerta)
    return _saida(alerta, db.get(Cliente, alerta.cliente_id) if alerta.cliente_id else None)


@router.get("/notificacoes", response_model=Pagina[NotificacaoOut])
def listar_notificacoes(
    usuario: UsuarioAtual, db: DbSession,
    canal: str | None = None, status_notificacao: str | None = Query(default=None, alias="status"),
    pagina: int = Query(1, ge=1), tamanho: int = Query(50, ge=1, le=500),
) -> Pagina[NotificacaoOut]:
    consulta = select(Notificacao).where(Notificacao.organizacao_id == usuario.organizacao_id)
    if canal:
        consulta = consulta.where(Notificacao.canal == canal)
    if status_notificacao:
        consulta = consulta.where(Notificacao.status == status_notificacao)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = list(db.scalars(
        consulta.order_by(Notificacao.created_at.desc())
        .offset((pagina - 1) * tamanho).limit(tamanho)
    ))
    return Pagina(itens=[NotificacaoOut.model_validate(n) for n in itens], total=total,
                  pagina=pagina, tamanho=tamanho)


@router.post("/notificacoes/enviar-pendentes")
def enviar(usuario: SomenteAdmin, db: DbSession) -> dict[str, Any]:
    resultado = enviar_pendentes(db, usuario.organizacao_id)
    db.commit()
    return resultado


@router.get("/regras", response_model=list[RegraOut])
def listar_regras(usuario: UsuarioAtual, db: DbSession) -> list[RegraMonitoramento]:
    return list(db.scalars(
        select(RegraMonitoramento)
        .where(RegraMonitoramento.organizacao_id == usuario.organizacao_id)
        .order_by(RegraMonitoramento.nome)
    ))


@router.post("/regras", response_model=RegraOut, status_code=201)
def criar_regra(dados: RegraIn, usuario: SomenteAdmin, db: DbSession) -> RegraMonitoramento:
    regra = RegraMonitoramento(
        organizacao_id=usuario.organizacao_id,
        nome=dados.nome,
        tipo_monitoramento=str(dados.tipo_monitoramento),
        ativo=dados.ativo,
        cron=dados.cron,
        criticidade_minima=str(dados.criticidade_minima),
        canais=[str(c) for c in dados.canais],
        clientes_escopo=dados.clientes_escopo,
        destinatarios=dados.destinatarios,
        parametros=dados.parametros,
    )
    db.add(regra)
    registrar(db, acao="CRIACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="REGRA", descricao=dados.nome)
    db.commit()
    db.refresh(regra)
    from app.services.agendador import recarregar

    recarregar()
    return regra


@router.patch("/regras/{regra_id}", response_model=RegraOut)
def alterar_regra(
    regra_id: str, dados: dict[str, Any], usuario: SomenteAdmin, db: DbSession
) -> RegraMonitoramento:
    regra = db.get(RegraMonitoramento, regra_id)
    if regra is None or regra.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra não encontrada.")
    for campo in ("nome", "tipo_monitoramento", "ativo", "cron", "criticidade_minima",
                  "canais", "clientes_escopo", "destinatarios", "parametros"):
        if campo in dados:
            setattr(regra, campo, dados[campo])
    registrar(db, acao="ALTERACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="REGRA", entidade_id=regra.id, detalhe=dados)
    db.commit()
    db.refresh(regra)
    from app.services.agendador import recarregar

    recarregar()
    return regra


@router.delete("/regras/{regra_id}", status_code=204)
def excluir_regra(regra_id: str, usuario: SomenteAdmin, db: DbSession) -> None:
    regra = db.get(RegraMonitoramento, regra_id)
    if regra is None or regra.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra não encontrada.")
    db.delete(regra)
    registrar(db, acao="EXCLUSAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="REGRA", entidade_id=regra_id)
    db.commit()
    from app.services.agendador import recarregar

    recarregar()
