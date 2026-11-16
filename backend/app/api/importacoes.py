"""Importação de planilhas de clientes/PER-DCOMP/procurações."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession, PodeEscrever, UsuarioAtual
from app.core.auditoria import registrar
from app.models.importacao import Importacao, ImportacaoLinha
from app.services import importacao as svc

router = APIRouter(prefix="/importacoes", tags=["Importação"])


def _obter(db, importacao_id: str, organizacao_id: str) -> Importacao:
    importacao = db.get(Importacao, importacao_id)
    if importacao is None or importacao.organizacao_id != organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Importação não encontrada.")
    return importacao


@router.get("/campos")
def campos_suportados(_: UsuarioAtual) -> list[dict[str, Any]]:
    return [
        {"nome": c.nome, "label": c.label, "tipo": c.tipo, "entidade": c.entidade,
         "obrigatorio": c.obrigatorio, "sinonimos": list(c.sinonimos)}
        for c in svc.CAMPOS
    ]


@router.get("/modelo")
def baixar_modelo(_: UsuarioAtual) -> StreamingResponse:
    """Planilha modelo (.xlsx) com as colunas esperadas e exemplos."""
    from app.services.planilha import gerar_modelo

    conteudo = gerar_modelo()
    return StreamingResponse(
        iter([conteudo]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo-importacao.xlsx"'},
    )


@router.post("", status_code=201)
async def enviar(
    usuario: PodeEscrever, db: DbSession,
    arquivo: UploadFile = File(...),
    mapeamento: str | None = Form(default=None),
) -> dict[str, Any]:
    import json

    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio.")
    if len(conteudo) > 20 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo acima de 20 MB.")
    manual = json.loads(mapeamento) if mapeamento else None
    try:
        importacao = svc.criar_importacao(
            db, organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
            usuario_email=usuario.email, nome_arquivo=arquivo.filename or "planilha",
            conteudo=conteudo, mapeamento_manual=manual,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    registrar(db, acao="IMPORTACAO_CARREGADA", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="IMPORTACAO",
              entidade_id=importacao.id, detalhe={"arquivo": importacao.arquivo_nome,
                                                  "linhas": importacao.total_linhas})
    db.commit()
    return _detalhe(db, importacao)


def _detalhe(db, importacao: Importacao) -> dict[str, Any]:
    linhas = list(db.scalars(
        select(ImportacaoLinha).where(ImportacaoLinha.importacao_id == importacao.id)
        .order_by(ImportacaoLinha.numero_linha)
    ))
    return {
        "id": importacao.id,
        "arquivo_nome": importacao.arquivo_nome,
        "status": importacao.status,
        "total_linhas": importacao.total_linhas,
        "mapeamento": importacao.mapeamento,
        "colunas_detectadas": importacao.colunas_detectadas,
        "colunas_ignoradas": importacao.colunas_ignoradas,
        "resumo": importacao.resumo,
        "criado_em": importacao.created_at.isoformat(),
        "confirmado_em": importacao.confirmado_em.isoformat() if importacao.confirmado_em else None,
        "linhas": [
            {
                "id": linha.id, "numero_linha": linha.numero_linha, "acao": linha.acao,
                "selecionada": linha.selecionada, "erros": linha.erros, "avisos": linha.avisos,
                "dados": linha.dados_normalizados, "dados_brutos": linha.dados_brutos,
                "cliente_id": linha.cliente_id, "resultado": linha.resultado,
                "corrigida": linha.corrigida, "duplicada_de_linha": linha.duplicada_de_linha,
            }
            for linha in linhas
        ],
    }


@router.get("")
def listar(usuario: UsuarioAtual, db: DbSession) -> list[dict[str, Any]]:
    importacoes = db.scalars(
        select(Importacao).where(Importacao.organizacao_id == usuario.organizacao_id)
        .order_by(Importacao.created_at.desc()).limit(100)
    )
    return [
        {"id": i.id, "arquivo_nome": i.arquivo_nome, "status": i.status,
         "total_linhas": i.total_linhas, "resumo": i.resumo,
         "usuario_email": i.usuario_email, "criado_em": i.created_at.isoformat(),
         "confirmado_em": i.confirmado_em.isoformat() if i.confirmado_em else None}
        for i in importacoes
    ]


@router.get("/{importacao_id}")
def detalhar(importacao_id: str, usuario: UsuarioAtual, db: DbSession) -> dict[str, Any]:
    return _detalhe(db, _obter(db, importacao_id, usuario.organizacao_id))


@router.patch("/{importacao_id}/linhas/{linha_id}")
def corrigir(
    importacao_id: str, linha_id: str, payload: dict[str, Any],
    usuario: PodeEscrever, db: DbSession,
) -> dict[str, Any]:
    importacao = _obter(db, importacao_id, usuario.organizacao_id)
    if importacao.status == "CONFIRMADO":
        raise HTTPException(status.HTTP_409_CONFLICT, "Importação já confirmada.")
    linha = db.get(ImportacaoLinha, linha_id)
    if linha is None or linha.importacao_id != importacao.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Linha não encontrada.")
    svc.corrigir_linha(
        db, linha, payload.get("correcoes") or {},
        organizacao_id=usuario.organizacao_id, selecionada=payload.get("selecionada"),
    )
    importacao.resumo = svc.resumir(db, importacao)
    registrar(db, acao="IMPORTACAO_CORRECAO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="IMPORTACAO_LINHA",
              entidade_id=linha.id, detalhe=payload)
    db.commit()
    return {"linha": {"id": linha.id, "numero_linha": linha.numero_linha, "acao": linha.acao,
                      "erros": linha.erros, "avisos": linha.avisos,
                      "dados": linha.dados_normalizados, "selecionada": linha.selecionada},
            "resumo": importacao.resumo}


@router.post("/{importacao_id}/confirmar")
def confirmar(
    importacao_id: str, usuario: PodeEscrever, db: DbSession,
    criar_estado_simulado: bool | None = None,
) -> dict[str, Any]:
    importacao = _obter(db, importacao_id, usuario.organizacao_id)
    try:
        resumo = svc.confirmar(
            db, importacao, usuario_id=usuario.id, usuario_email=usuario.email,
            criar_estado_simulado=criar_estado_simulado,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    registrar(db, acao="IMPORTACAO_CONFIRMADA", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="IMPORTACAO",
              entidade_id=importacao.id, detalhe={k: v for k, v in resumo.items()
                                                  if k != "detalhes"})
    db.commit()
    return {"importacao_id": importacao.id, "status": importacao.status, "resumo": resumo}


@router.post("/{importacao_id}/cancelar")
def cancelar(importacao_id: str, usuario: PodeEscrever, db: DbSession) -> dict[str, str]:
    importacao = _obter(db, importacao_id, usuario.organizacao_id)
    if importacao.status == "CONFIRMADO":
        raise HTTPException(status.HTTP_409_CONFLICT, "Importação confirmada não pode ser cancelada.")
    importacao.status = "CANCELADO"
    db.commit()
    return {"detalhe": "Importação cancelada."}
