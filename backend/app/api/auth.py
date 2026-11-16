"""Autenticação e gestão de usuários."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession, SomenteAdmin, UsuarioAtual, client_ip
from app.core.auditoria import registrar
from app.core.db import utcnow
from app.core.security import (
    criar_access_token,
    hash_senha,
    validar_forca_senha,
    verificar_senha,
)
from app.models.tenant import Usuario
from app.schemas.auth import LoginIn, TokenOut, TrocaSenhaIn, UsuarioIn, UsuarioOut

router = APIRouter(tags=["Autenticação"])


@router.post("/auth/login", response_model=TokenOut)
def login(dados: LoginIn, request: Request, db: DbSession) -> TokenOut:
    usuario = db.scalar(select(Usuario).where(Usuario.email == str(dados.email).lower()))
    ip = client_ip(request)
    if usuario is None or not verificar_senha(dados.senha, usuario.senha_hash):
        if usuario is not None:
            usuario.tentativas_falhas += 1
        registrar(db, acao="LOGIN_FALHA", usuario_email=str(dados.email).lower(), ip=ip,
                  user_agent=request.headers.get("user-agent"),
                  organizacao_id=usuario.organizacao_id if usuario else None, commit=True)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos.")
    if not usuario.ativo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário desativado.")

    usuario.ultimo_login = utcnow()
    usuario.tentativas_falhas = 0
    token, expira = criar_access_token(
        usuario_id=usuario.id, organizacao_id=usuario.organizacao_id,
        perfil=usuario.perfil, email=usuario.email,
    )
    registrar(db, acao="LOGIN", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, ip=ip, user_agent=request.headers.get("user-agent"))
    db.commit()
    return TokenOut(access_token=token, expira_em=expira, usuario=UsuarioOut.model_validate(usuario))


@router.get("/auth/me", response_model=UsuarioOut)
def eu(usuario: UsuarioAtual) -> Usuario:
    return usuario


@router.post("/auth/trocar-senha")
def trocar_senha(dados: TrocaSenhaIn, usuario: UsuarioAtual, db: DbSession) -> dict[str, str]:
    if not verificar_senha(dados.senha_atual, usuario.senha_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")
    problemas = validar_forca_senha(dados.senha_nova)
    if problemas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(problemas))
    usuario.senha_hash = hash_senha(dados.senha_nova)
    usuario.deve_trocar_senha = False
    registrar(db, acao="TROCA_SENHA", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="USUARIO",
              entidade_id=usuario.id)
    db.commit()
    return {"detalhe": "Senha alterada."}


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(admin: SomenteAdmin, db: DbSession) -> list[Usuario]:
    return list(db.scalars(
        select(Usuario).where(Usuario.organizacao_id == admin.organizacao_id)
        .order_by(Usuario.nome)
    ))


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def criar_usuario(dados: UsuarioIn, admin: SomenteAdmin, db: DbSession) -> Usuario:
    problemas = validar_forca_senha(dados.senha)
    if problemas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(problemas))
    email = str(dados.email).lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado.")
    usuario = Usuario(
        organizacao_id=admin.organizacao_id, nome=dados.nome, email=email,
        senha_hash=hash_senha(dados.senha), perfil=str(dados.perfil),
    )
    db.add(usuario)
    registrar(db, acao="CRIACAO", organizacao_id=admin.organizacao_id, usuario_id=admin.id,
              usuario_email=admin.email, entidade="USUARIO", descricao=f"Criou usuário {email}")
    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioOut)
def alterar_usuario(
    usuario_id: str, dados: dict, admin: SomenteAdmin, db: DbSession
) -> Usuario:
    alvo = db.get(Usuario, usuario_id)
    if alvo is None or alvo.organizacao_id != admin.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    for campo in ("nome", "perfil", "ativo"):
        if campo in dados:
            setattr(alvo, campo, dados[campo])
    if dados.get("senha"):
        problemas = validar_forca_senha(dados["senha"])
        if problemas:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(problemas))
        alvo.senha_hash = hash_senha(dados["senha"])
        alvo.deve_trocar_senha = True
    registrar(db, acao="ALTERACAO", organizacao_id=admin.organizacao_id, usuario_id=admin.id,
              usuario_email=admin.email, entidade="USUARIO", entidade_id=alvo.id,
              detalhe={k: v for k, v in dados.items() if k != "senha"})
    db.commit()
    db.refresh(alvo)
    return alvo
