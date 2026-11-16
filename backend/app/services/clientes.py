"""Cadastro de clientes com histórico de alterações campo a campo."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models.cliente import Cliente, ClienteHistorico
from app.models.enums import OrigemInformacao

CAMPOS_EDITAVEIS = (
    "razao_social", "nome_fantasia", "email", "responsavel",
    "tributos_trabalhados", "telefone", "observacoes", "ativo",
)


def buscar_por_cnpj(db: Session, organizacao_id: str, cnpj: str) -> Cliente | None:
    return db.scalar(
        select(Cliente).where(Cliente.organizacao_id == organizacao_id, Cliente.cnpj == cnpj)
    )


def registrar_historico(
    db: Session, cliente: Cliente, campo: str, anterior: Any, novo: Any,
    *, origem: str = OrigemInformacao.MANUAL, usuario_id: str | None = None,
    usuario_email: str | None = None, referencia: dict[str, Any] | None = None,
) -> None:
    db.add(
        ClienteHistorico(
            cliente_id=cliente.id,
            campo=campo,
            valor_anterior=None if anterior is None else str(anterior),
            valor_novo=None if novo is None else str(novo),
            origem=str(origem),
            usuario_id=usuario_id,
            usuario_email=usuario_email,
            referencia=referencia,
            created_at=utcnow(),
        )
    )


def criar_cliente(
    db: Session, *, organizacao_id: str, cnpj: str, dados: dict[str, Any],
    origem: str = OrigemInformacao.MANUAL, usuario_id: str | None = None,
    usuario_email: str | None = None,
) -> Cliente:
    cliente = Cliente(
        organizacao_id=organizacao_id,
        cnpj=cnpj,
        razao_social=dados.get("razao_social") or f"CNPJ {cnpj}",
    )
    for campo in CAMPOS_EDITAVEIS:
        if campo in dados and dados[campo] is not None:
            setattr(cliente, campo, dados[campo])
    db.add(cliente)
    db.flush()
    registrar_historico(
        db, cliente, "cadastro", None, "criado", origem=origem,
        usuario_id=usuario_id, usuario_email=usuario_email,
    )
    return cliente


def atualizar_cliente(
    db: Session, cliente: Cliente, dados: dict[str, Any], *,
    origem: str = OrigemInformacao.MANUAL, usuario_id: str | None = None,
    usuario_email: str | None = None, sobrescrever_vazios: bool = False,
) -> list[str]:
    """Atualiza campos e devolve a lista de campos efetivamente alterados."""
    alterados: list[str] = []
    for campo in CAMPOS_EDITAVEIS:
        if campo not in dados:
            continue
        novo = dados[campo]
        if novo is None or (isinstance(novo, str) and not novo.strip()):
            if not sobrescrever_vazios:
                continue
        atual = getattr(cliente, campo)
        if str(atual or "") == str(novo or ""):
            continue
        setattr(cliente, campo, novo)
        alterados.append(campo)
        registrar_historico(
            db, cliente, campo, atual, novo, origem=origem,
            usuario_id=usuario_id, usuario_email=usuario_email,
        )
    return alterados
