"""Painel e operações de procurações eletrônicas."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select

from app.api.deps import DbSession, PodeEscrever, SomenteAdmin, UsuarioAtual
from app.connectors.registry import conector_procuracao
from app.core.auditoria import registrar
from app.models.cliente import Cliente
from app.models.enums import Semaforo, SituacaoProcuracao
from app.models.procuracao import Procuracao, ProcuracaoConsulta
from app.schemas.comum import Pagina
from app.schemas.dominio import (
    ProcuracaoConsultaOut,
    ProcuracaoIn,
    ProcuracaoOut,
    ProcuracaoUpdate,
)
from app.services import procuracoes as svc
from app.services.cnpj import formatar_cnpj, limpar

router = APIRouter(prefix="/procuracoes", tags=["Procurações"])


def _saida(proc: Procuracao, cliente: Cliente | None) -> ProcuracaoOut:
    out = ProcuracaoOut.model_validate(proc)
    out.semaforo = svc.semaforo(proc)
    out.dias_para_vencer = svc.dias_para_vencer(proc)
    if cliente:
        out.cliente_razao_social = cliente.razao_social
        out.cliente_cnpj = formatar_cnpj(cliente.cnpj)
    return out


@router.get("", response_model=Pagina[ProcuracaoOut])
def listar(
    usuario: UsuarioAtual, db: DbSession,
    busca: str | None = None, semaforo: Semaforo | None = None,
    situacao: str | None = None, responsavel: str | None = None,
    vence_em_dias: int | None = Query(default=None, ge=0, le=3650),
    pagina: int = Query(1, ge=1), tamanho: int = Query(50, ge=1, le=500),
) -> Pagina[ProcuracaoOut]:
    consulta = (
        select(Procuracao, Cliente)
        .join(Cliente, Cliente.id == Procuracao.cliente_id)
        .where(Procuracao.organizacao_id == usuario.organizacao_id)
    )
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(or_(
            Cliente.razao_social.ilike(termo),
            Cliente.cnpj.like(f"%{limpar(busca) or busca}%"),
            Procuracao.numero.ilike(termo),
        ))
    if situacao:
        consulta = consulta.where(Procuracao.situacao == situacao)
    if responsavel:
        consulta = consulta.where(Cliente.responsavel == responsavel)
    if vence_em_dias is not None:
        from datetime import timedelta
        consulta = consulta.where(
            Procuracao.data_fim.is_not(None),
            Procuracao.data_fim <= date.today() + timedelta(days=vence_em_dias),
        )
    linhas = list(db.execute(consulta.order_by(Procuracao.data_fim.is_(None), Procuracao.data_fim)))
    itens = [_saida(p, c) for p, c in linhas]
    if semaforo is not None:
        itens = [i for i in itens if i.semaforo == semaforo]
    total = len(itens)
    inicio = (pagina - 1) * tamanho
    return Pagina(itens=itens[inicio:inicio + tamanho], total=total, pagina=pagina, tamanho=tamanho)


@router.get("/painel")
def painel(usuario: UsuarioAtual, db: DbSession) -> dict[str, Any]:
    """Visão de semáforo + próximos vencimentos."""
    linhas = list(db.execute(
        select(Procuracao, Cliente)
        .join(Cliente, Cliente.id == Procuracao.cliente_id)
        .where(Procuracao.organizacao_id == usuario.organizacao_id)
    ))
    contagem = {str(s): 0 for s in Semaforo}
    proximos: list[dict[str, Any]] = []
    for proc, cliente in linhas:
        sem = str(svc.semaforo(proc))
        contagem[sem] += 1
        dias = svc.dias_para_vencer(proc)
        if dias is not None and -30 <= dias <= 60:
            proximos.append({
                "procuracao_id": proc.id, "numero": proc.numero,
                "cliente_id": cliente.id, "razao_social": cliente.razao_social,
                "cnpj": formatar_cnpj(cliente.cnpj), "data_fim": proc.data_fim.isoformat(),
                "dias_para_vencer": dias, "semaforo": sem, "situacao": proc.situacao,
                "validada_por_fonte": proc.validada_por_fonte,
                "disponibilidade": proc.disponibilidade,
            })
    proximos.sort(key=lambda x: x["dias_para_vencer"])
    return {
        "semaforo": contagem,
        "legenda": {
            "VERDE": "Procuração ativa validada por fonte autorizada.",
            "AMARELO": "Validada e próxima do vencimento (<= 30 dias).",
            "VERMELHO": "Expirada ou revogada conforme a fonte.",
            "CINZA": "Situação desconhecida: sem validação ou consulta indisponível.",
        },
        "proximos_vencimentos": proximos[:50],
        "faixas_alerta_dias": sorted(__import__("app.core.config", fromlist=["settings"])
                                     .settings.alerta_procuracao_dias),
    }


@router.get("/{procuracao_id}", response_model=ProcuracaoOut)
def detalhar(procuracao_id: str, usuario: UsuarioAtual, db: DbSession) -> ProcuracaoOut:
    proc = db.get(Procuracao, procuracao_id)
    if proc is None or proc.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procuração não encontrada.")
    return _saida(proc, db.get(Cliente, proc.cliente_id))


@router.get("/{procuracao_id}/consultas", response_model=list[ProcuracaoConsultaOut])
def consultas(procuracao_id: str, usuario: UsuarioAtual, db: DbSession) -> list[ProcuracaoConsulta]:
    proc = db.get(Procuracao, procuracao_id)
    if proc is None or proc.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procuração não encontrada.")
    return list(db.scalars(
        select(ProcuracaoConsulta).where(ProcuracaoConsulta.procuracao_id == procuracao_id)
        .order_by(ProcuracaoConsulta.consultado_em.desc()).limit(200)
    ))


@router.post("", response_model=ProcuracaoOut, status_code=201)
def criar(dados: ProcuracaoIn, usuario: PodeEscrever, db: DbSession) -> ProcuracaoOut:
    cliente = db.get(Cliente, dados.cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    proc, _ = svc.upsert_procuracao(db, cliente, dados.model_dump(exclude={"cliente_id"}),
                                    origem="MANUAL")
    registrar(db, acao="CRIACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="PROCURACAO", entidade_id=proc.id)
    db.commit()
    db.refresh(proc)
    return _saida(proc, cliente)


@router.patch("/{procuracao_id}", response_model=ProcuracaoOut)
def alterar(
    procuracao_id: str, dados: ProcuracaoUpdate, usuario: PodeEscrever, db: DbSession
) -> ProcuracaoOut:
    """Edita os dados cadastrais da procuração.

    Editar à mão NÃO torna a procuração validada: `validada_por_fonte` continua
    como está e a situação do sistema é recalculada apenas como *declarada*.
    """
    proc = db.get(Procuracao, procuracao_id)
    if proc is None or proc.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procuração não encontrada.")
    alterados: dict[str, Any] = {}
    for campo, valor in dados.model_dump(exclude_none=True).items():
        atual = getattr(proc, campo)
        if str(atual or "") != str(valor or ""):
            alterados[campo] = {"de": str(atual) if atual is not None else None, "para": str(valor)}
            setattr(proc, campo, valor)
    proc.situacao_declarada = svc.situacao_por_data(proc.data_fim)
    if not proc.validada_por_fonte:
        proc.situacao = SituacaoProcuracao.DESCONHECIDA
    registrar(db, acao="ALTERACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="PROCURACAO", entidade_id=proc.id,
              detalhe={"campos": alterados})
    db.commit()
    db.refresh(proc)
    return _saida(proc, db.get(Cliente, proc.cliente_id))


@router.delete("/{procuracao_id}", status_code=204)
def excluir(procuracao_id: str, admin: SomenteAdmin, db: DbSession) -> None:
    """Exclui a procuração e seu histórico de consultas (restrito a ADMIN)."""
    proc = db.get(Procuracao, procuracao_id)
    if proc is None or proc.organizacao_id != admin.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procuração não encontrada.")
    registrar(db, acao="EXCLUSAO", organizacao_id=admin.organizacao_id, usuario_id=admin.id,
              usuario_email=admin.email, entidade="PROCURACAO", entidade_id=proc.id,
              detalhe={"numero": proc.numero, "cliente_id": proc.cliente_id})
    db.delete(proc)
    db.commit()


@router.post("/{procuracao_id}/consultar", response_model=dict)
def consultar_agora(
    procuracao_id: str, usuario: PodeEscrever, db: DbSession
) -> dict[str, Any]:
    proc = db.get(Procuracao, procuracao_id)
    if proc is None or proc.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procuração não encontrada.")
    cliente = db.get(Cliente, proc.cliente_id)
    conector = conector_procuracao(db)
    resultado = conector.consultar(cnpj=cliente.cnpj, numero=proc.numero)
    diff = svc.registrar_consulta(db, proc, resultado, usuario_email=usuario.email)
    registrar(db, acao="CONSULTA_FONTE", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="PROCURACAO",
              entidade_id=proc.id, detalhe={"disponibilidade": diff["disponibilidade"]})
    db.commit()
    db.refresh(proc)
    return {"procuracao": _saida(proc, cliente).model_dump(mode="json"), "consulta": diff}
