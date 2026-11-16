"""Armazenamento de anexos: validação, gravação em disco e metadados.

Decisões de segurança:
  * o binário NÃO vai para o banco — fica em volume dedicado, fora do webroot;
  * o nome enviado pelo usuário nunca compõe o caminho em disco (evita
    *path traversal*); guarda-se o nome original apenas como metadado;
  * tipo e tamanho são validados por extensão **e** por assinatura do conteúdo;
  * cada arquivo tem SHA-256 registrado, o que permite detectar duplicidade e
    comprovar integridade depois;
  * downloads de documentos marcados como restritos exigem perfil ADMIN e todo
    acesso é registrado na trilha de auditoria.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.models.cliente import Cliente
from app.models.documento import Documento
from app.models.enums import CategoriaDocumento

# extensão -> (mime, assinaturas aceitas; vazio = não verificável)
TIPOS_PERMITIDOS: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK\x03\x04",)),
    ".xls": ("application/vnd.ms-excel", (b"\xd0\xcf\x11\xe0", b"PK\x03\x04")),
    ".csv": ("text/csv", ()),
    ".txt": ("text/plain", ()),
    ".xml": ("application/xml", ()),
}

ENTIDADES_VALIDAS = {"CLIENTE", "COMPENSACAO", "PROCURACAO", "SITUACAO_FISCAL"}


class ErroDocumento(ValueError):
    """Falha de validação ao anexar um documento."""


def raiz_arquivos() -> Path:
    base = (
        Path(settings.arquivos_dir)
        if settings.arquivos_dir
        else Path(__file__).resolve().parents[2].parent / "arquivos"
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def _nome_seguro(nome: str) -> str:
    limpo = unicodedata.normalize("NFKD", nome or "arquivo")
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    limpo = re.sub(r"[^A-Za-z0-9._-]+", "_", limpo).strip("._")
    return (limpo or "arquivo")[:120]


def validar(nome_arquivo: str, conteudo: bytes) -> tuple[str, str]:
    """Valida extensão, tamanho e assinatura. Devolve (nome seguro, mime)."""
    if not conteudo:
        raise ErroDocumento("Arquivo vazio.")
    limite = settings.upload_max_mb * 1024 * 1024
    if len(conteudo) > limite:
        raise ErroDocumento(
            f"Arquivo com {len(conteudo) / 1048576:.1f} MB excede o limite de "
            f"{settings.upload_max_mb} MB."
        )
    nome = _nome_seguro(nome_arquivo)
    extensao = Path(nome).suffix.lower()
    if extensao not in TIPOS_PERMITIDOS:
        raise ErroDocumento(
            f"Extensão '{extensao or 'sem extensão'}' não permitida. "
            f"Aceitas: {', '.join(sorted(TIPOS_PERMITIDOS))}."
        )
    mime, assinaturas = TIPOS_PERMITIDOS[extensao]
    if assinaturas and not any(conteudo.startswith(a) for a in assinaturas):
        raise ErroDocumento(
            f"O conteúdo do arquivo não corresponde a um {extensao} válido."
        )
    return nome, mime


def anexar(
    db: Session, cliente: Cliente, *, nome_arquivo: str, conteudo: bytes,
    categoria: str, entidade: str = "CLIENTE", entidade_id: str | None = None,
    descricao: str | None = None, data_documento: datetime | None = None,
    restrito: bool = False, usuario_email: str | None = None,
) -> tuple[Documento, Documento | None]:
    """Grava o arquivo e registra os metadados.

    Devolve (documento, duplicado) — `duplicado` é um anexo anterior do mesmo
    cliente com conteúdo idêntico, quando existir.
    """
    nome, mime = validar(nome_arquivo, conteudo)
    if categoria not in set(CategoriaDocumento):
        raise ErroDocumento(f"Categoria inválida: {categoria}.")
    if entidade not in ENTIDADES_VALIDAS:
        raise ErroDocumento(f"Entidade inválida: {entidade}.")

    digest = hashlib.sha256(conteudo).hexdigest()
    duplicado = db.scalar(
        select(Documento).where(
            Documento.cliente_id == cliente.id, Documento.sha256 == digest
        )
    )

    relativo = Path(cliente.organizacao_id) / cliente.id / f"{uuid.uuid4().hex}{Path(nome).suffix.lower()}"
    destino = raiz_arquivos() / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    destino.chmod(0o640)

    documento = Documento(
        organizacao_id=cliente.organizacao_id,
        cliente_id=cliente.id,
        entidade=entidade,
        entidade_id=entidade_id,
        categoria=categoria,
        nome_original=nome,
        caminho_relativo=str(relativo),
        tipo_mime=mime,
        tamanho_bytes=len(conteudo),
        sha256=digest,
        descricao=descricao,
        data_documento=data_documento,
        restrito=restrito,
        enviado_por=usuario_email,
        created_at=utcnow(),
    )
    db.add(documento)
    db.flush()
    return documento, duplicado


def caminho_absoluto(documento: Documento) -> Path:
    """Resolve o caminho em disco, barrando qualquer saída da raiz."""
    raiz = raiz_arquivos().resolve()
    caminho = (raiz / documento.caminho_relativo).resolve()
    if not str(caminho).startswith(str(raiz)):
        raise ErroDocumento("Caminho de arquivo inválido.")
    return caminho


def ler(documento: Documento) -> bytes:
    caminho = caminho_absoluto(documento)
    if not caminho.is_file():
        raise ErroDocumento("Arquivo não encontrado no armazenamento.")
    conteudo = caminho.read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != documento.sha256:
        raise ErroDocumento("Integridade do arquivo comprometida (hash divergente).")
    return conteudo


def remover(db: Session, documento: Documento) -> None:
    caminho = caminho_absoluto(documento)
    if caminho.is_file():
        caminho.unlink()
    db.delete(documento)
    db.flush()


def listar(
    db: Session, organizacao_id: str, *, cliente_id: str | None = None,
    entidade: str | None = None, entidade_id: str | None = None,
    categoria: str | None = None,
) -> list[Documento]:
    consulta = select(Documento).where(Documento.organizacao_id == organizacao_id)
    if cliente_id:
        consulta = consulta.where(Documento.cliente_id == cliente_id)
    if entidade:
        consulta = consulta.where(Documento.entidade == entidade)
    if entidade_id:
        consulta = consulta.where(Documento.entidade_id == entidade_id)
    if categoria:
        consulta = consulta.where(Documento.categoria == categoria)
    return list(db.scalars(consulta.order_by(Documento.created_at.desc())))


def como_dict(documento: Documento) -> dict[str, Any]:
    return {
        "id": documento.id,
        "cliente_id": documento.cliente_id,
        "entidade": documento.entidade,
        "entidade_id": documento.entidade_id,
        "categoria": documento.categoria,
        "nome_original": documento.nome_original,
        "tipo_mime": documento.tipo_mime,
        "tamanho_bytes": documento.tamanho_bytes,
        "sha256": documento.sha256,
        "descricao": documento.descricao,
        "data_documento": documento.data_documento.isoformat() if documento.data_documento else None,
        "restrito": documento.restrito,
        "enviado_por": documento.enviado_por,
        "created_at": documento.created_at.isoformat(),
    }
