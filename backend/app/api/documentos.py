"""Anexos: upload, listagem, download controlado e exclusão."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.api.deps import DbSession, PodeEscrever, SomenteAdmin, UsuarioAtual
from app.core.auditoria import registrar
from app.models.cliente import Cliente
from app.models.documento import Documento
from app.models.enums import CategoriaDocumento, Perfil
from app.services import documentos as svc

router = APIRouter(prefix="/documentos", tags=["Documentos"])


def _cliente(db, cliente_id: str, organizacao_id: str) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return cliente


def _documento(db, documento_id: str, organizacao_id: str) -> Documento:
    documento = db.get(Documento, documento_id)
    if documento is None or documento.organizacao_id != organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    return documento


@router.get("/categorias")
def categorias(_: UsuarioAtual) -> list[dict[str, str]]:
    rotulos = {
        CategoriaDocumento.DESPACHO_DECISORIO: "Despacho decisório",
        CategoriaDocumento.INTIMACAO: "Intimação / exigência",
        CategoriaDocumento.RELATORIO_SITUACAO_FISCAL: "Relatório de situação fiscal",
        CategoriaDocumento.COMPROVANTE_PERDCOMP: "Comprovante / recibo de PER/DCOMP",
        CategoriaDocumento.PROCURACAO: "Procuração",
        CategoriaDocumento.CONTRATO: "Contrato",
        CategoriaDocumento.OUTRO: "Outro",
    }
    return [{"codigo": str(k), "rotulo": v} for k, v in rotulos.items()]


@router.get("/limites")
def limites(_: UsuarioAtual) -> dict[str, Any]:
    from app.core.config import settings

    return {
        "tamanho_maximo_mb": settings.upload_max_mb,
        "extensoes_aceitas": sorted(svc.TIPOS_PERMITIDOS),
        "observacao": "O tipo é conferido pela extensão e pela assinatura do conteúdo.",
    }


@router.get("")
def listar(
    usuario: UsuarioAtual, db: DbSession,
    cliente_id: str | None = None, entidade: str | None = None,
    entidade_id: str | None = None, categoria: str | None = None,
) -> list[dict[str, Any]]:
    documentos = svc.listar(
        db, usuario.organizacao_id, cliente_id=cliente_id, entidade=entidade,
        entidade_id=entidade_id, categoria=categoria,
    )
    saida = []
    for documento in documentos:
        item = svc.como_dict(documento)
        # Documento restrito aparece na lista, mas o download exige ADMIN.
        item["pode_baixar"] = (not documento.restrito) or usuario.perfil == Perfil.ADMIN
        saida.append(item)
    return saida


@router.post("", status_code=201)
async def enviar(
    usuario: PodeEscrever, db: DbSession,
    arquivo: UploadFile = File(...),
    cliente_id: str = Form(...),
    categoria: str = Form(default=str(CategoriaDocumento.OUTRO)),
    entidade: str = Form(default="CLIENTE"),
    entidade_id: str | None = Form(default=None),
    descricao: str | None = Form(default=None),
    data_documento: str | None = Form(default=None),
    restrito: bool = Form(default=False),
) -> dict[str, Any]:
    cliente = _cliente(db, cliente_id, usuario.organizacao_id)
    conteudo = await arquivo.read()
    data = None
    if data_documento:
        try:
            data = datetime.fromisoformat(data_documento)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Data do documento inválida (use AAAA-MM-DD).") from None
    try:
        documento, duplicado = svc.anexar(
            db, cliente, nome_arquivo=arquivo.filename or "arquivo", conteudo=conteudo,
            categoria=categoria, entidade=entidade, entidade_id=entidade_id or None,
            descricao=descricao, data_documento=data, restrito=restrito,
            usuario_email=usuario.email,
        )
    except svc.ErroDocumento as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    registrar(db, acao="DOCUMENTO_ANEXADO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="DOCUMENTO",
              entidade_id=documento.id,
              descricao=f"{documento.categoria}: {documento.nome_original}",
              detalhe={"cliente_id": cliente.id, "sha256": documento.sha256,
                       "tamanho_bytes": documento.tamanho_bytes, "restrito": documento.restrito})
    db.commit()
    db.refresh(documento)
    resposta = svc.como_dict(documento)
    resposta["pode_baixar"] = True
    if duplicado is not None:
        resposta["aviso"] = (
            f"Conteúdo idêntico ao documento '{duplicado.nome_original}' "
            f"enviado em {duplicado.created_at.strftime('%d/%m/%Y')}."
        )
    return resposta


@router.get("/{documento_id}/download")
def baixar(documento_id: str, usuario: UsuarioAtual, db: DbSession, request_ip: str | None = None
           ) -> Response:
    documento = _documento(db, documento_id, usuario.organizacao_id)
    if documento.restrito and usuario.perfil != Perfil.ADMIN:
        registrar(db, acao="DOCUMENTO_ACESSO_NEGADO", organizacao_id=usuario.organizacao_id,
                  usuario_id=usuario.id, usuario_email=usuario.email, entidade="DOCUMENTO",
                  entidade_id=documento.id, commit=True)
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Documento restrito: download permitido apenas ao perfil ADMIN.")
    try:
        conteudo = svc.ler(documento)
    except svc.ErroDocumento as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc

    registrar(db, acao="DOCUMENTO_VISUALIZADO", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="DOCUMENTO",
              entidade_id=documento.id, ip=request_ip,
              descricao=f"Download de {documento.nome_original}", commit=True)
    return Response(
        content=conteudo, media_type=documento.tipo_mime,
        headers={"Content-Disposition": f'attachment; filename="{documento.nome_original}"',
                 "Content-Length": str(len(conteudo))},
    )


@router.delete("/{documento_id}", status_code=204)
def excluir(documento_id: str, admin: SomenteAdmin, db: DbSession) -> None:
    documento = _documento(db, documento_id, admin.organizacao_id)
    registrar(db, acao="DOCUMENTO_EXCLUIDO", organizacao_id=admin.organizacao_id,
              usuario_id=admin.id, usuario_email=admin.email, entidade="DOCUMENTO",
              entidade_id=documento.id,
              descricao=f"{documento.categoria}: {documento.nome_original}",
              detalhe={"sha256": documento.sha256, "cliente_id": documento.cliente_id})
    svc.remover(db, documento)
    db.commit()
