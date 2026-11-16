"""Situação fiscal: snapshots e comparação entre consultas.

O comparativo descreve **o que** mudou (novos débitos, baixados, remanescentes,
alterados) e nunca afirma **por que** mudou. Toda redução vem acompanhada de
ressalva explícita de que a causa não é presumida.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ResultadoConsulta
from app.core.crypto import content_hash
from app.core.db import utcnow
from app.core.serial import para_json
from app.models.cliente import Cliente
from app.models.enums import CategoriaPendencia, Disponibilidade, SituacaoFiscalGeral
from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
from app.services.parsers import parse_decimal, texto_ou_none

RESSALVA_PADRAO = (
    "A variação apresentada é a diferença entre duas consultas e NÃO implica "
    "relação de causa e efeito com as compensações realizadas. Pagamentos, "
    "parcelamentos, retificações, decisões administrativas e atualização de "
    "sistemas da Receita Federal também alteram estes valores."
)

_CATEGORIA_TOTAL = {
    CategoriaPendencia.DEBITO_PREVIDENCIARIO: "total_previdenciario",
    CategoriaPendencia.DEBITO_FEDERAL: "total_federal",
    CategoriaPendencia.DEBITO_EM_COBRANCA: "total_em_cobranca",
    CategoriaPendencia.DEBITO_SUSPENSO: "total_suspenso",
    CategoriaPendencia.PARCELAMENTO: "total_parcelado",
}

# Débitos suspensos e parcelamentos não entram no "total em aberto exigível".
_NAO_SOMA_TOTAL = {CategoriaPendencia.DEBITO_SUSPENSO, CategoriaPendencia.PARCELAMENTO}


def chave_pendencia(item: dict[str, Any]) -> str:
    """Identidade estável de uma pendência para comparação entre consultas."""
    if item.get("chave"):
        return str(item["chave"])
    partes = [
        str(item.get("categoria") or ""),
        str(item.get("codigo") or item.get("descricao") or "")[:60],
        str(item.get("periodo") or ""),
    ]
    return "|".join(partes).upper()


def normalizar_pendencias(brutas: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    saida: list[dict[str, Any]] = []
    for item in brutas or []:
        categoria = texto_ou_none(item.get("categoria")) or CategoriaPendencia.OUTROS
        if categoria not in set(CategoriaPendencia):
            categoria = CategoriaPendencia.OUTROS
        valor = parse_decimal(item.get("valor")) or Decimal("0")
        normalizado = {
            "categoria": str(categoria),
            "codigo": texto_ou_none(item.get("codigo")),
            "descricao": texto_ou_none(item.get("descricao")) or "Pendência sem descrição",
            "periodo": texto_ou_none(item.get("periodo")),
            "valor": str(valor),
            "situacao": texto_ou_none(item.get("situacao")),
            "processo": texto_ou_none(item.get("processo")),
        }
        normalizado["chave"] = chave_pendencia({**item, **normalizado})
        saida.append(normalizado)
    return saida


def criar_snapshot(
    db: Session, cliente: Cliente, resultado: ResultadoConsulta,
    *, referencia_evento: str | None = None, usuario_email: str | None = None,
) -> SituacaoFiscalSnapshot:
    dados = resultado.dados if isinstance(resultado.dados, dict) else {}
    pendencias = normalizar_pendencias(dados.get("pendencias"))

    totais = {campo: Decimal("0") for campo in set(_CATEGORIA_TOTAL.values())}
    total_geral = Decimal("0")
    acessorias = 0
    for item in pendencias:
        valor = Decimal(item["valor"])
        categoria = item["categoria"]
        campo = _CATEGORIA_TOTAL.get(categoria)
        if campo:
            totais[campo] += valor
        if categoria == CategoriaPendencia.OBRIGACAO_ACESSORIA:
            acessorias += 1
        if categoria not in _NAO_SOMA_TOTAL:
            total_geral += valor

    if resultado.disponibilidade == Disponibilidade.OK:
        informada = texto_ou_none(dados.get("situacao_geral"))
        if informada in set(SituacaoFiscalGeral):
            situacao_geral = informada
        else:
            situacao_geral = (
                SituacaoFiscalGeral.COM_PENDENCIAS if pendencias else SituacaoFiscalGeral.REGULAR
            )
    elif resultado.disponibilidade == Disponibilidade.SEM_DADOS or resultado.disponibilidade == Disponibilidade.NAO_CONSULTADO:
        situacao_geral = SituacaoFiscalGeral.NAO_CONSULTADO
    else:
        situacao_geral = SituacaoFiscalGeral.INDISPONIVEL

    snapshot = SituacaoFiscalSnapshot(
        organizacao_id=cliente.organizacao_id,
        cliente_id=cliente.id,
        origem=str(resultado.origem),
        disponibilidade=str(resultado.disponibilidade),
        situacao_geral=str(situacao_geral),
        total_debitos=total_geral,
        total_previdenciario=totais["total_previdenciario"],
        total_federal=totais["total_federal"],
        total_em_cobranca=totais["total_em_cobranca"],
        total_suspenso=totais["total_suspenso"],
        total_parcelado=totais["total_parcelado"],
        qtd_pendencias=len(pendencias),
        qtd_obrigacoes_acessorias=acessorias,
        pendencias=para_json(pendencias),
        mensagem=resultado.mensagem,
        relatorio_bruto=texto_ou_none(dados.get("relatorio_bruto")),
        hash_conteudo=content_hash({"p": pendencias, "s": str(situacao_geral)}),
        consultado_em=resultado.consultado_em,
        criado_por=usuario_email,
        referencia_evento=referencia_evento,
    )
    db.add(snapshot)
    cliente.ultima_consulta_fiscal = resultado.consultado_em
    db.flush()
    return snapshot


def ultimo_snapshot(
    db: Session, cliente_id: str, *, excluir_id: str | None = None, somente_ok: bool = True
) -> SituacaoFiscalSnapshot | None:
    consulta = (
        select(SituacaoFiscalSnapshot)
        .where(SituacaoFiscalSnapshot.cliente_id == cliente_id)
        .order_by(SituacaoFiscalSnapshot.consultado_em.desc())
    )
    if somente_ok:
        consulta = consulta.where(SituacaoFiscalSnapshot.disponibilidade == Disponibilidade.OK)
    if excluir_id:
        consulta = consulta.where(SituacaoFiscalSnapshot.id != excluir_id)
    return db.scalars(consulta.limit(1)).first()


def comparar(
    db: Session, cliente: Cliente,
    anterior: SituacaoFiscalSnapshot, atual: SituacaoFiscalSnapshot,
    *, persistir: bool = True,
) -> SituacaoFiscalComparativo:
    antes = {p["chave"]: p for p in (anterior.pendencias or [])}
    depois = {p["chave"]: p for p in (atual.pendencias or [])}

    novos = [v for k, v in depois.items() if k not in antes]
    baixados = [v for k, v in antes.items() if k not in depois]
    permanecem: list[dict[str, Any]] = []
    alterados: list[dict[str, Any]] = []
    for chave, item in depois.items():
        if chave not in antes:
            continue
        valor_antes = Decimal(antes[chave]["valor"])
        valor_depois = Decimal(item["valor"])
        if valor_antes != valor_depois:
            alterados.append({
                **item,
                "valor_anterior": str(valor_antes),
                "valor_atual": str(valor_depois),
                "variacao": str(valor_depois - valor_antes),
            })
        else:
            permanecem.append(item)

    comparativo = SituacaoFiscalComparativo(
        organizacao_id=cliente.organizacao_id,
        cliente_id=cliente.id,
        snapshot_anterior_id=anterior.id,
        snapshot_atual_id=atual.id,
        total_anterior=anterior.total_debitos,
        total_atual=atual.total_debitos,
        diferenca=Decimal(str(atual.total_debitos)) - Decimal(str(anterior.total_debitos)),
        novos=novos,
        baixados=baixados,
        permanecem=permanecem,
        alterados=alterados,
        ressalva=RESSALVA_PADRAO,
        created_at=utcnow(),
    )
    if persistir:
        db.add(comparativo)
        db.flush()
    return comparativo
