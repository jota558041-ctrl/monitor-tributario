"""Dependências de API: sessão, usuário autenticado e controle de acesso."""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decodificar_token
from app.models.enums import Perfil
from app.models.tenant import Usuario

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_usuario_atual(
    request: Request,
    db: DbSession,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Usuario:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciais ausentes.")
    try:
        payload = decodificar_token(cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada.") from None
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido.") from None

    usuario = db.get(Usuario, payload["sub"])
    if usuario is None or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo ou inexistente.")
    if usuario.organizacao_id != payload.get("org"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organização divergente do token.")
    request.state.usuario = usuario
    return usuario


UsuarioAtual = Annotated[Usuario, Depends(get_usuario_atual)]


def exige_perfil(*perfis: Perfil) -> Callable[..., Usuario]:
    permitidos = {p.value for p in perfis}

    def _verificador(usuario: UsuarioAtual) -> Usuario:
        if usuario.perfil not in permitidos:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Ação restrita aos perfis: {', '.join(sorted(permitidos))}.",
            )
        return usuario

    return _verificador


SomenteAdmin = Annotated[Usuario, Depends(exige_perfil(Perfil.ADMIN))]
# Auditor tem acesso de leitura; escrita exige ADMIN ou ANALISTA.
PodeEscrever = Annotated[Usuario, Depends(exige_perfil(Perfil.ADMIN, Perfil.ANALISTA))]


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
