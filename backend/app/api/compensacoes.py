"""Monitoramento das compensações (PER/DCOMP)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, PodeEscrever, SomenteAdmin, UsuarioAtual
from app.connectors.base import ResultadoConsulta
from app.connectors.registry import conector_compensacao
from app.core.auditoria import registrar
from app.core.db import utcnow
from app.core.serial import para_json
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao, CompensacaoEvento
from app.models.enums import Disponibilidade, OrigemInformacao, SituacaoCompensacao
from app.schemas.comum import Pagina
from app.schemas.dominio import (
    CompensacaoEventoOut,
    CompensacaoIn,
    CompensacaoOut,
    CompensacaoResultadoManualIn,
    CompensacaoUpdate,
)
from app.services import compensacoes as svc
from app.services.cnpj import formatar_cnpj, limpar

router = APIRouter(prefix="/compensacoes", tags=["Compensações"])

CLASSIFICACOES = {
    SituacaoCompensacao.TRANSMITIDA: "Declaração transmitida; sem análise concluída.",
    SituacaoCompensacao.EM_PROCESSAMENTO: "Em processamento pelos sistemas da RFB.",
    SituacaoCompensacao.EM_ANALISE: "Em análise (crédito sob verificação).",
    SituacaoCompensacao.HOMOLOGADA: "Compensação homologada integralmente.",
    SituacaoCompensacao.NAO_HOMOLOGADA: "Compensação não homologada.",
    SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE: "Homologada em parte; há saldo não homologado.",
    SituacaoCompensacao.CANCELADA: "Declaração cancelada/retificada.",
    SituacaoCompensacao.COM_EXIGENCIA: "Há exigência ou intimação pendente de resposta.",
    SituacaoCompensacao.SEM_INFORMACAO: "Sem informação atualizada da fonte (não é homologação).",
}


def _saida(comp: Compensacao, cliente: Cliente | None) -> CompensacaoOut:
    out = CompensacaoOut.model_validate(comp)
    if cliente:
        out.cliente_razao_social = cliente.razao_social
        out.cliente_cnpj = formatar_cnpj(cliente.cnpj)
    return out


@router.get("/classificacoes")
def classificacoes(_: UsuarioAtual) -> list[dict[str, str]]:
    return [{"codigo": str(k), "descricao": v} for k, v in CLASSIFICACOES.items()]


@router.get("", response_model=Pagina[CompensacaoOut])
def listar(
    usuario: UsuarioAtual, db: DbSession,
    busca: str | None = None, situacao: SituacaoCompensacao | None = None,
    tributo: str | None = None, responsavel: str | None = None,
    cliente_id: str | None = None,
    data_inicio: date | None = None, data_fim: date | None = None,
    pagina: int = Query(1, ge=1), tamanho: int = Query(50, ge=1, le=500),
) -> Pagina[CompensacaoOut]:
    consulta = (
        select(Compensacao, Cliente)
        .join(Cliente, Cliente.id == Compensacao.cliente_id)
        .where(Compensacao.organizacao_id == usuario.organizacao_id)
    )
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(or_(
            Compensacao.numero_perdcomp.ilike(termo),
            Cliente.razao_social.ilike(termo),
            Cliente.cnpj.like(f"%{limpar(busca) or busca}%"),
        ))
    if situacao:
        consulta = consulta.where(Compensacao.situacao_compensacao == situacao)
    if tributo:
        consulta = consulta.where(Compensacao.tributo.ilike(f"%{tributo}%"))
    if responsavel:
        consulta = consulta.where(Cliente.responsavel == responsavel)
    if cliente_id:
        consulta = consulta.where(Compensacao.cliente_id == cliente_id)
    if data_inicio:
        consulta = consulta.where(Compensacao.data_transmissao >= data_inicio)
    if data_fim:
        consulta = consulta.where(Compensacao.data_transmissao <= data_fim)

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    linhas = list(db.execute(
        consulta.order_by(Compensacao.data_transmissao.desc().nullslast())
        .offset((pagina - 1) * tamanho).limit(tamanho)
    ))
    return Pagina(itens=[_saida(c, cli) for c, cli in linhas], total=total,
                  pagina=pagina, tamanho=tamanho)


@router.get("/tributos", response_model=list[str])
def tributos(usuario: UsuarioAtual, db: DbSession) -> list[str]:
    return list(db.scalars(
        select(Compensacao.tributo)
        .where(Compensacao.organizacao_id == usuario.organizacao_id,
               Compensacao.tributo.is_not(None))
        .distinct().order_by(Compensacao.tributo)
    ))


@router.get("/{compensacao_id}", response_model=CompensacaoOut)
def detalhar(compensacao_id: str, usuario: UsuarioAtual, db: DbSession) -> CompensacaoOut:
    comp = db.get(Compensacao, compensacao_id)
    if comp is None or comp.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compensação não encontrada.")
    return _saida(comp, db.get(Cliente, comp.cliente_id))


@router.get("/{compensacao_id}/historico", response_model=list[CompensacaoEventoOut])
def historico(
    compensacao_id: str, usuario: UsuarioAtual, db: DbSession
) -> list[CompensacaoEvento]:
    comp = db.get(Compensacao, compensacao_id)
    if comp is None or comp.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compensação não encontrada.")
    return list(db.scalars(
        select(CompensacaoEvento).where(CompensacaoEvento.compensacao_id == compensacao_id)
        .order_by(CompensacaoEvento.registrado_em.desc()).limit(300)
    ))


@router.post("", response_model=CompensacaoOut, status_code=201)
def criar(dados: CompensacaoIn, usuario: PodeEscrever, db: DbSession) -> CompensacaoOut:
    cliente = db.get(Cliente, dados.cliente_id)
    if cliente is None or cliente.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    comp, _ = svc.upsert_compensacao(
        db, cliente, dados.model_dump(exclude={"cliente_id"}),
        origem=OrigemInformacao.MANUAL, usuario_email=usuario.email,
    )
    registrar(db, acao="CRIACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="COMPENSACAO", entidade_id=comp.id)
    db.commit()
    db.refresh(comp)
    return _saida(comp, cliente)


@router.patch("/{compensacao_id}", response_model=CompensacaoOut)
def alterar(
    compensacao_id: str, dados: CompensacaoUpdate, usuario: PodeEscrever, db: DbSession
) -> CompensacaoOut:
    """Edita os dados declarados da PER/DCOMP.

    A *situação da compensação* não muda por aqui: para isso existe a consulta à
    fonte ou o registro de resultado oficial, que gravam origem e data.
    """
    comp = db.get(Compensacao, compensacao_id)
    if comp is None or comp.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compensação não encontrada.")
    alterados: dict[str, Any] = {}
    for campo, valor in dados.model_dump(exclude_none=True).items():
        atual = getattr(comp, campo)
        if str(atual or "") != str(valor or ""):
            alterados[campo] = {"de": str(atual) if atual is not None else None, "para": str(valor)}
            setattr(comp, campo, valor)
    if alterados:
        db.add(CompensacaoEvento(
            compensacao_id=comp.id, tipo="EDICAO_MANUAL",
            situacao_anterior=comp.situacao_compensacao, situacao_nova=comp.situacao_compensacao,
            origem=OrigemInformacao.MANUAL, disponibilidade=comp.disponibilidade,
            mensagem=f"Dados declarados editados por {usuario.email}.",
            payload=para_json({"campos": alterados}), registrado_em=utcnow(),
            criado_por=usuario.email,
        ))
    registrar(db, acao="ALTERACAO", organizacao_id=usuario.organizacao_id, usuario_id=usuario.id,
              usuario_email=usuario.email, entidade="COMPENSACAO", entidade_id=comp.id,
              detalhe={"campos": alterados})
    db.commit()
    db.refresh(comp)
    return _saida(comp, db.get(Cliente, comp.cliente_id))


@router.delete("/{compensacao_id}", status_code=204)
def excluir(compensacao_id: str, admin: SomenteAdmin, db: DbSession) -> None:
    """Exclui a PER/DCOMP e seu histórico (restrito a ADMIN)."""
    comp = db.get(Compensacao, compensacao_id)
    if comp is None or comp.organizacao_id != admin.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compensação não encontrada.")
    registrar(db, acao="EXCLUSAO", organizacao_id=admin.organizacao_id, usuario_id=admin.id,
              usuario_email=admin.email, entidade="COMPENSACAO", entidade_id=comp.id,
              detalhe={"numero_perdcomp": comp.numero_perdcomp, "cliente_id": comp.cliente_id})
    db.delete(comp)
    db.commit()


@router.post("/{compensacao_id}/consultar")
def consultar_agora(
    compensacao_id: str, usuario: PodeEscrever, db: DbSession
) -> dict[str, Any]:
    comp = db.get(Compensacao, compensacao_id)
    if comp is None or comp.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compensação não encontrada.")
    cliente = db.get(Cliente, comp.cliente_id)
    resultado = conector_compensacao(db).consultar(
        cnpj=cliente.cnpj, numero_perdcomp=comp.numero_perdcomp
    )
    diff = svc.registrar_consulta(db, comp, resultado, usuario_email=usuario.email)
    registrar(db, acao="CONSULTA_FONTE", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="COMPENSACAO",
              entidade_id=comp.id, detalhe={"disponibilidade": diff["disponibilidade"]})
    db.commit()
    db.refresh(comp)
    return {"compensacao": _saida(comp, cliente).model_dump(mode="json"), "consulta": diff}


@router.post("/{compensacao_id}/resultado-manual")
def registrar_resultado_manual(
    compensacao_id: str, dados: CompensacaoResultadoManualIn,
    usuario: PodeEscrever, db: DbSession,
) -> dict[str, Any]:
    """Registra resultado obtido fora do sistema (e-CAC / PER-DCOMP Web).

    Usado quando não há consulta automática autorizada. A informação fica
    marcada com origem IMPORTACAO_RELATORIO e a data informada pelo usuário.
    """
    comp = db.get(Compensacao, compensacao_id)
    if comp is None or comp.organizacao_id != usuario.organizacao_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compensação não encontrada.")
    payload = dados.model_dump(exclude={"consultado_em", "fonte_descricao", "observacoes"})
    payload = {k: v for k, v in payload.items() if v is not None}
    resultado = ResultadoConsulta(
        disponibilidade=Disponibilidade.OK,
        origem=OrigemInformacao.IMPORTACAO_RELATORIO,
        fonte_descricao=dados.fonte_descricao,
        consultado_em=dados.consultado_em or utcnow(),
        dados=para_json(payload),
        mensagem=f"Resultado informado manualmente por {usuario.email}."
                 + (f" Obs.: {dados.observacoes}" if dados.observacoes else ""),
    )
    diff = svc.registrar_consulta(db, comp, resultado, usuario_email=usuario.email)
    registrar(db, acao="RESULTADO_MANUAL", organizacao_id=usuario.organizacao_id,
              usuario_id=usuario.id, usuario_email=usuario.email, entidade="COMPENSACAO",
              entidade_id=comp.id, detalhe={"situacao": comp.situacao_compensacao})
    db.commit()
    db.refresh(comp)
    return {"compensacao": _saida(comp, db.get(Cliente, comp.cliente_id)).model_dump(mode="json"),
            "consulta": diff}
