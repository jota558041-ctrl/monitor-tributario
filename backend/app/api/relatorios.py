"""Exportação de relatórios em Excel e PDF."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import DbSession, UsuarioAtual
from app.core.auditoria import registrar
from app.models.cliente import Cliente
from app.models.tenant import Organizacao
from app.services import relatorios as svc
from app.services.cnpj import limpar

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _contexto(db, usuario) -> dict[str, Any]:
    org = db.get(Organizacao, usuario.organizacao_id)
    return {"usuario": usuario.email, "organizacao": org.nome if org else "",
            "filtros": "nenhum"}


def _entrega(conteudo: bytes, nome: str, tipo: str) -> Response:
    return Response(
        content=conteudo, media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nome}"',
                 "Content-Length": str(len(conteudo))},
    )


@router.get("/carteira.xlsx")
def carteira(
    usuario: UsuarioAtual, db: DbSession, responsavel: str | None = None
) -> Response:
    """Carteira consolidada: clientes, procurações, PER/DCOMP e situação fiscal."""
    contexto = _contexto(db, usuario)
    if responsavel:
        contexto["filtros"] = f"responsável = {responsavel}"
    conteudo = svc.carteira_excel(db, usuario.organizacao_id, contexto=contexto,
                                  responsavel=responsavel)
    registrar(db, acao="RELATORIO_GERADO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="RELATORIO",
              descricao="Carteira consolidada (xlsx)", detalhe={"responsavel": responsavel},
              commit=True)
    hoje = datetime.now(UTC).strftime("%Y-%m-%d")
    return _entrega(conteudo, f"carteira-{hoje}.xlsx", XLSX)


@router.get("/alertas.xlsx")
def alertas(
    usuario: UsuarioAtual, db: DbSession,
    dias: int = Query(90, ge=1, le=1825), status_alerta: str | None = Query(None, alias="status"),
) -> Response:
    """Relação de alertas do período, com explicação e evidência de cada um."""
    contexto = _contexto(db, usuario)
    contexto["filtros"] = f"últimos {dias} dia(s)" + (f", status = {status_alerta}" if status_alerta else "")
    desde = datetime.now(UTC) - timedelta(days=dias)
    conteudo = svc.alertas_excel(db, usuario.organizacao_id, contexto=contexto,
                                 desde=desde, status=status_alerta)
    registrar(db, acao="RELATORIO_GERADO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="RELATORIO",
              descricao="Relação de alertas (xlsx)", detalhe={"dias": dias, "status": status_alerta},
              commit=True)
    hoje = datetime.now(UTC).strftime("%Y-%m-%d")
    return _entrega(conteudo, f"alertas-{hoje}.xlsx", XLSX)


@router.get("/consultas.xlsx")
def consultas(
    usuario: UsuarioAtual, db: DbSession,
    cliente_id: str | None = None, dias: int = Query(90, ge=1, le=1825),
) -> Response:
    """Extrato de consultas realizadas — prestação de contas ao cliente."""
    if cliente_id:
        cliente = db.get(Cliente, cliente_id)
        if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    contexto = _contexto(db, usuario)
    contexto["filtros"] = f"últimos {dias} dia(s)" + (" · cliente específico" if cliente_id else "")
    conteudo = svc.extrato_consultas_excel(db, usuario.organizacao_id, contexto=contexto,
                                           cliente_id=cliente_id, dias=dias)
    registrar(db, acao="RELATORIO_GERADO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="RELATORIO",
              descricao="Extrato de consultas (xlsx)",
              detalhe={"cliente_id": cliente_id, "dias": dias}, commit=True)
    hoje = datetime.now(UTC).strftime("%Y-%m-%d")
    return _entrega(conteudo, f"extrato-consultas-{hoje}.xlsx", XLSX)


@router.get("/cliente/{cliente_id}.pdf")
def cliente_pdf(cliente_id: str, usuario: UsuarioAtual, db: DbSession) -> Response:
    """Posição tributária completa de um cliente, em PDF."""
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    conteudo = svc.cliente_pdf(db, cliente, contexto=_contexto(db, usuario))
    registrar(db, acao="RELATORIO_GERADO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="CLIENTE",
              entidade_id=cliente.id, descricao="Posição do cliente (pdf)", commit=True)
    hoje = datetime.now(UTC).strftime("%Y-%m-%d")
    return _entrega(conteudo, f"posicao-{limpar(cliente.cnpj)}-{hoje}.pdf", "application/pdf")
