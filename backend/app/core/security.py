"""Autenticação: hash de senha (bcrypt) e tokens JWT."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode()


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8")[:72], senha_hash.encode())
    except (ValueError, TypeError):
        return False


def validar_forca_senha(senha: str) -> list[str]:
    problemas: list[str] = []
    if len(senha) < settings.password_min_length:
        problemas.append(f"A senha deve ter ao menos {settings.password_min_length} caracteres.")
    if not any(c.isdigit() for c in senha):
        problemas.append("A senha deve conter ao menos um número.")
    if not any(c.isalpha() for c in senha):
        problemas.append("A senha deve conter ao menos uma letra.")
    if not any(not c.isalnum() for c in senha):
        problemas.append("A senha deve conter ao menos um caractere especial.")
    return problemas


def criar_access_token(
    *, usuario_id: str, organizacao_id: str, perfil: str, email: str,
    expira_minutos: int | None = None,
) -> tuple[str, datetime]:
    expira = datetime.now(UTC) + timedelta(
        minutes=expira_minutos or settings.access_token_minutes
    )
    payload: dict[str, Any] = {
        "sub": usuario_id,
        "org": organizacao_id,
        "perfil": perfil,
        "email": email,
        "exp": expira,
        "iat": datetime.now(UTC),
        "iss": settings.app_name,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expira


def decodificar_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
