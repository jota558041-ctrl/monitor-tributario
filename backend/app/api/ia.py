"""Camada de interpretação: resumos e lista de clientes para atenção."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, UsuarioAtual
from app.core.auditoria import registrar
from app.ia import resumo as svc
from app.models.cliente import Cliente

router = APIRouter(prefix="/ia", tags=["Interpretação (IA)"])


@router.get("/clientes-atencao")
def clientes_atencao(
    usuario: UsuarioAtual, db: DbSession, limite: int = Query(20, ge=1, le=200)
) -> dict[str, Any]:
    itens = svc.clientes_para_atencao(db, usuario.organizacao_id, limite=limite)
    return {
        "itens": itens,
        "criterio": "Soma ponderada da criticidade dos alertas abertos por cliente.",
        "limites": [
            "A ordenação é estatística, não jurídica.",
            "Cada item traz os alertas e suas evidências para conferência humana.",
        ],
    }


@router.get("/resumo/{cliente_id}")
def resumo_cliente(
    cliente_id: str, usuario: UsuarioAtual, db: DbSession, usar_llm: bool | None = None
) -> dict[str, Any]:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    saida = svc.resumo_cliente(db, cliente, usar_llm=usar_llm)
    registrar(db, acao="IA_RESUMO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="CLIENTE", entidade_id=cliente.id,
              detalhe={"metodo": saida["metodo"]}, commit=True)
    return saida
