"""Criptografia de dados em repouso (campos sensíveis) + hashing de conteúdo.

Política de segurança implementada:
  * Nunca armazenamos senha gov.br.
  * Chaves privadas de certificado digital NÃO são persistidas no banco: apenas o
    caminho do arquivo em volume protegido e a senha cifrada com Fernet.
  * Campos sensíveis usam TipoCriptografado (SQLAlchemy TypeDecorator).
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _build_key() -> bytes:
    if settings.fernet_key:
        return settings.fernet_key.encode()
    # Derivação determinística para ambiente de desenvolvimento/teste.
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_build_key())


def encrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def content_hash(payload: Any) -> str:
    """Hash estável do conteúdo de uma consulta (detecção de mudança real)."""
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()
