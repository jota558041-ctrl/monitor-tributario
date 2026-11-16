from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Perfil
from app.schemas.comum import Base


class LoginIn(BaseModel):
    """O login não valida sintaxe de e-mail: apenas confronta credenciais."""
    email: str = Field(min_length=3, max_length=180)
    senha: str = Field(min_length=1)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: datetime
    usuario: UsuarioOut


class UsuarioOut(Base):
    id: str
    nome: str
    email: str
    perfil: Perfil
    ativo: bool
    organizacao_id: str
    ultimo_login: datetime | None = None


class UsuarioIn(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    perfil: Perfil = Perfil.ANALISTA


class TrocaSenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str


TokenOut.model_rebuild()
