"""Cadastro de clientes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, PodeEscrever, UsuarioAtual, client_ip
from app.core.auditoria import registrar
from app.models.cliente import Cliente, ClienteHistorico
from app.schemas.comum import Pagina
from app.schemas.dominio import ClienteIn, ClienteOut, ClienteUpdate, HistoricoOut
from app.services import clientes as svc
from app.services.cnpj import cnpj_valido, formatar_cnpj, limpar

router = APIRouter(prefix="/clientes", tags=["Clientes"])


def _saida(cliente: Cliente) -> ClienteOut:
    out = ClienteOut.model_validate(cliente)
    out.cnpj_formatado = formatar_cnpj(cliente.cnpj)
    return out


@router.get("", response_model=Pagina[ClienteOut])
def listar(
    usuario: UsuarioAtual, db: DbSession,
    busca: str | None = None, responsavel: str | None = None,
    ativo: bool | None = None, pagina: int = Query(1, ge=1),
    tamanho: int = Query(50, ge=1, le=500),
) -> Pagina[ClienteOut]:
    consulta = select(Cliente).where(Cliente.organizacao_id == usuario.organizacao_id)
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(or_(
            Cliente.cnpj.like(f"%{limpar(busca)}%") if limpar(busca) else Cliente.cnpj.like(termo),
            Cliente.razao_social.ilike(termo),
            Cliente.nome_fantasia.ilike(termo),
        ))
    if responsavel:
        consulta = consulta.where(Cliente.responsavel == responsavel)
    if ativo is not None:
        consulta = consulta.where(Cliente.ativo.is_(ativo))

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = list(db.scalars(
        consulta.order_by(Cliente.razao_social).offset((pagina - 1) * tamanho).limit(tamanho)
    ))
    return Pagina(itens=[_saida(c) for c in itens], total=total, pagina=pagina, tamanho=tamanho)


@router.get("/responsaveis", response_model=list[str])
def responsaveis(usuario: UsuarioAtual, db: DbSession) -> list[str]:
    return list(db.scalars(
        select(Cliente.responsavel)
        .where(Cliente.organizacao_id == usuario.organizacao_id,
               Cliente.responsavel.is_not(None))
        .distinct().order_by(Cliente.responsavel)
    ))


@router.get("/{cliente_id}", response_model=ClienteOut)
def detalhar(cliente_id: str, usuario: UsuarioAtual, db: DbSession, request: Request) -> ClienteOut:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    registrar(db, acao="LEITURA", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="CLIENTE", entidade_id=cliente.id,
              ip=client_ip(request), commit=True)
    return _saida(cliente)


@router.get("/{cliente_id}/historico", response_model=list[HistoricoOut])
def historico(cliente_id: str, usuario: UsuarioAtual, db: DbSession) -> list[ClienteHistorico]:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return list(db.scalars(
        select(ClienteHistorico).where(ClienteHistorico.cliente_id == cliente_id)
        .order_by(ClienteHistorico.created_at.desc()).limit(500)
    ))


@router.post("", response_model=ClienteOut, status_code=201)
def criar(dados: ClienteIn, usuario: PodeEscrever, db: DbSession) -> ClienteOut:
    cnpj = limpar(dados.cnpj)
    if not cnpj_valido(cnpj):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"CNPJ inválido: {dados.cnpj}")
    if svc.buscar_por_cnpj(db, usuario.organizacao_id, cnpj):
        raise HTTPException(status.HTTP_409_CONFLICT, "CNPJ já cadastrado nesta organização.")
    cliente = svc.criar_cliente(
        db, organizacao_id=usuario.organizacao_id, cnpj=cnpj,
        dados=dados.model_dump(exclude={"cnpj"}), usuario_id=usuario.id,
        usuario_email=usuario.email,
    )
    registrar(db, acao="CRIACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="CLIENTE", entidade_id=cliente.id)
    db.commit()
    db.refresh(cliente)
    return _saida(cliente)


@router.patch("/{cliente_id}", response_model=ClienteOut)
def alterar(
    cliente_id: str, dados: ClienteUpdate, usuario: PodeEscrever, db: DbSession
) -> ClienteOut:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    alterados = svc.atualizar_cliente(
        db, cliente, dados.model_dump(exclude_none=True),
        usuario_id=usuario.id, usuario_email=usuario.email,
    )
    registrar(db, acao="ALTERACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="CLIENTE", entidade_id=cliente.id,
              detalhe={"campos": alterados})
    db.commit()
    db.refresh(cliente)
    return _saida(cliente)
