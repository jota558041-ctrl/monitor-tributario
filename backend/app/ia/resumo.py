"""Resumo por cliente e lista de clientes que exigem atenção.

Determinístico por padrão. A redação por LLM é opcional e recebe APENAS os
fatos já apurados, com instrução explícita de não acrescentar informação; se a
chamada falhar, o texto determinístico é mantido.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ia.analise import AVISO_HUMANO, _brl
from app.models.alerta import Alerta
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao
from app.models.enums import (
    ORDEM_CRITICIDADE,
    Criticidade,
    Disponibilidade,
    SituacaoCompensacao,
    SituacaoFiscalGeral,
    StatusAlerta,
)
from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
from app.models.procuracao import Procuracao
from app.services.cnpj import formatar_cnpj
from app.services.procuracoes import dias_para_vencer, semaforo

PESO_CRITICIDADE = {Criticidade.CRITICA: 40, Criticidade.ALTA: 25,
                    Criticidade.MEDIA: 12, Criticidade.BAIXA: 5, Criticidade.INFO: 1}


def _ultimo_snapshot(db: Session, cliente_id: str) -> SituacaoFiscalSnapshot | None:
    return db.scalars(
        select(SituacaoFiscalSnapshot)
        .where(SituacaoFiscalSnapshot.cliente_id == cliente_id)
        .order_by(SituacaoFiscalSnapshot.consultado_em.desc())
        .limit(1)
    ).first()


def montar_fatos(db: Session, cliente: Cliente) -> dict[str, Any]:
    """Coleta os fatos apurados (sem interpretação) de um cliente."""
    procuracoes = db.scalars(
        select(Procuracao).where(Procuracao.cliente_id == cliente.id)
    ).all()
    compensacoes = db.scalars(
        select(Compensacao).where(Compensacao.cliente_id == cliente.id)
    ).all()
    snapshot = _ultimo_snapshot(db, cliente.id)
    comparativo = db.scalars(
        select(SituacaoFiscalComparativo)
        .where(SituacaoFiscalComparativo.cliente_id == cliente.id)
        .order_by(SituacaoFiscalComparativo.created_at.desc())
        .limit(1)
    ).first()
    alertas = db.scalars(
        select(Alerta).where(
            Alerta.cliente_id == cliente.id,
            Alerta.status.in_([StatusAlerta.NOVO, StatusAlerta.EM_ANALISE]),
        ).order_by(Alerta.gerado_em.desc())
    ).all()

    por_situacao: dict[str, int] = {}
    for comp in compensacoes:
        por_situacao[comp.situacao_compensacao] = por_situacao.get(comp.situacao_compensacao, 0) + 1

    return {
        "cliente": {
            "id": cliente.id, "cnpj": formatar_cnpj(cliente.cnpj),
            "razao_social": cliente.razao_social, "responsavel": cliente.responsavel,
        },
        "procuracoes": [
            {
                "numero": p.numero, "data_fim": p.data_fim.isoformat() if p.data_fim else None,
                "situacao": p.situacao, "situacao_declarada": p.situacao_declarada,
                "semaforo": str(semaforo(p)), "dias_para_vencer": dias_para_vencer(p),
                "validada_por_fonte": p.validada_por_fonte,
                "disponibilidade": p.disponibilidade,
                "consultado_em": p.consultado_em.isoformat() if p.consultado_em else None,
            }
            for p in procuracoes
        ],
        "compensacoes": {
            "total": len(compensacoes),
            "por_situacao": por_situacao,
            "valor_credito_total": str(sum(Decimal(str(c.valor_credito or 0)) for c in compensacoes)),
            "nao_homologado_total": str(
                sum(Decimal(str(c.valor_nao_homologado or 0)) for c in compensacoes)
            ),
            "itens": [
                {
                    "numero": c.numero_perdcomp, "situacao": c.situacao_compensacao,
                    "tributo": c.tributo, "periodo": c.periodo_apuracao,
                    "valor_credito": str(c.valor_credito or 0),
                    "disponibilidade": c.disponibilidade,
                    "consultado_em": c.consultado_em.isoformat() if c.consultado_em else None,
                }
                for c in compensacoes
            ],
        },
        "situacao_fiscal": None if snapshot is None else {
            "situacao_geral": snapshot.situacao_geral,
            "disponibilidade": snapshot.disponibilidade,
            "total_debitos": str(snapshot.total_debitos),
            "qtd_pendencias": snapshot.qtd_pendencias,
            "consultado_em": snapshot.consultado_em.isoformat(),
            "origem": snapshot.origem,
        },
        "comparativo": None if comparativo is None else {
            "total_anterior": str(comparativo.total_anterior),
            "total_atual": str(comparativo.total_atual),
            "diferenca": str(comparativo.diferenca),
            "novos": len(comparativo.novos or []),
            "baixados": len(comparativo.baixados or []),
            "permanecem": len(comparativo.permanecem or []),
            "ressalva": comparativo.ressalva,
        },
        "alertas_abertos": [
            {"tipo": a.tipo, "criticidade": a.criticidade, "titulo": a.titulo,
             "gerado_em": a.gerado_em.isoformat()}
            for a in alertas
        ],
    }


def resumo_deterministico(fatos: dict[str, Any]) -> list[str]:
    linhas: list[str] = []
    cli = fatos["cliente"]
    linhas.append(f"{cli['razao_social']} (CNPJ {cli['cnpj']})"
                  + (f" - responsável: {cli['responsavel']}" if cli.get("responsavel") else ""))

    procs = fatos["procuracoes"]
    if not procs:
        linhas.append("Procurações: nenhuma cadastrada.")
    else:
        for p in procs:
            if not p["validada_por_fonte"]:
                linhas.append(
                    f"Procuração {p['numero'] or 's/nº'}: situação NÃO validada por fonte "
                    f"(estado técnico {p['disponibilidade']}); na planilha constava "
                    f"'{p['situacao_declarada']}'. Semáforo CINZA."
                )
            else:
                venc = f", vence em {p['dias_para_vencer']} dia(s)" if p["dias_para_vencer"] is not None else ""
                linhas.append(
                    f"Procuração {p['numero'] or 's/nº'}: {p['situacao']}{venc} "
                    f"(validada em {p['consultado_em']}, semáforo {p['semaforo']})."
                )

    comp = fatos["compensacoes"]
    if comp["total"] == 0:
        linhas.append("PER/DCOMP: nenhuma cadastrada.")
    else:
        detalhe = ", ".join(f"{qtd} {sit}" for sit, qtd in sorted(comp["por_situacao"].items()))
        linhas.append(f"PER/DCOMP: {comp['total']} monitorada(s) - {detalhe}. "
                      f"Crédito informado: {_brl(comp['valor_credito_total'])}.")
        if Decimal(comp["nao_homologado_total"]) > 0:
            linhas.append(f"Valor não homologado acumulado: {_brl(comp['nao_homologado_total'])}.")
        sem_info = comp["por_situacao"].get(SituacaoCompensacao.SEM_INFORMACAO, 0)
        if sem_info:
            linhas.append(f"{sem_info} PER/DCOMP sem informação atualizada da fonte - "
                          "isso NÃO indica homologação nem indeferimento.")

    fiscal = fatos["situacao_fiscal"]
    if fiscal is None:
        linhas.append("Situação fiscal: nunca consultada neste sistema.")
    elif fiscal["disponibilidade"] != Disponibilidade.OK:
        linhas.append(f"Situação fiscal: última consulta sem resultado "
                      f"({fiscal['disponibilidade']}) em {fiscal['consultado_em']}. "
                      "Não há conclusão sobre regularidade.")
    elif fiscal["situacao_geral"] == SituacaoFiscalGeral.REGULAR:
        linhas.append(f"Situação fiscal: nenhuma pendência identificada na consulta de "
                      f"{fiscal['consultado_em']} (fonte {fiscal['origem']}).")
    else:
        linhas.append(f"Situação fiscal: {fiscal['qtd_pendencias']} pendência(s), total "
                      f"{_brl(fiscal['total_debitos'])} (consulta de {fiscal['consultado_em']}).")

    comparativo = fatos["comparativo"]
    if comparativo:
        dif = Decimal(comparativo["diferenca"])
        sentido = "redução" if dif < 0 else ("aumento" if dif > 0 else "estabilidade")
        linhas.append(
            f"Comparativo entre consultas: {_brl(comparativo['total_anterior'])} -> "
            f"{_brl(comparativo['total_atual'])} ({sentido} de {_brl(abs(dif))}); "
            f"{comparativo['novos']} novo(s), {comparativo['baixados']} baixado(s), "
            f"{comparativo['permanecem']} remanescente(s)."
        )
        linhas.append(comparativo["ressalva"])

    abertos = fatos["alertas_abertos"]
    if abertos:
        linhas.append(f"Alertas abertos: {len(abertos)} - "
                      + "; ".join(f"[{a['criticidade']}] {a['titulo']}" for a in abertos[:5]))
    else:
        linhas.append("Nenhum alerta aberto.")
    linhas.append(AVISO_HUMANO)
    return linhas


def refinar_com_llm(fatos: dict[str, Any], linhas: list[str]) -> tuple[str, str]:
    """Reescreve o resumo com LLM. Retorna (texto, metodo)."""
    if not (settings.ia_llm_enabled and settings.anthropic_api_key):
        return "\n".join(linhas), "REGRAS"
    try:
        import json

        import httpx

        prompt = (
            "Você redige resumos para uma equipe tributária. Reescreva os fatos abaixo em um "
            "parágrafo objetivo, em português do Brasil, SEM acrescentar nenhuma informação, "
            "SEM estimar valores, SEM afirmar homologação que não esteja nos fatos e SEM emitir "
            "parecer jurídico. Preserve datas, origens das consultas e ressalvas.\n\n"
            f"FATOS (JSON):\n{json.dumps(fatos, ensure_ascii=False)[:12000]}\n\n"
            f"RESUMO DETERMINÍSTICO:\n" + "\n".join(linhas)
        )
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.ia_llm_model, "max_tokens": 900,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60.0,
        )
        resp.raise_for_status()
        blocos = resp.json().get("content", [])
        texto = "\n".join(b.get("text", "") for b in blocos if b.get("type") == "text").strip()
        if texto:
            return texto, "LLM"
    except Exception:  # noqa: BLE001 - nunca falhar por causa do LLM
        pass
    return "\n".join(linhas), "REGRAS_FALLBACK"


def resumo_cliente(db: Session, cliente: Cliente, *, usar_llm: bool | None = None) -> dict[str, Any]:
    fatos = montar_fatos(db, cliente)
    linhas = resumo_deterministico(fatos)
    if usar_llm is None:
        usar_llm = settings.ia_llm_enabled
    if usar_llm:
        texto, metodo = refinar_com_llm(fatos, linhas)
    else:
        texto, metodo = "\n".join(linhas), "REGRAS"
    return {
        "cliente_id": cliente.id,
        "gerado_em": datetime.now(UTC).isoformat(),
        "metodo": metodo,
        "resumo": texto,
        "topicos": linhas,
        "fatos": fatos,
        "limites": [
            "A IA não cria informação fiscal: apenas descreve consultas gravadas.",
            "Não há declaração de homologação sem evidência da fonte.",
            "Não há interpretação jurídica definitiva; validação humana é obrigatória.",
        ],
    }


def clientes_para_atencao(
    db: Session, organizacao_id: str, *, limite: int = 20
) -> list[dict[str, Any]]:
    """Ranking de clientes por gravidade acumulada dos alertas abertos."""
    alertas = db.scalars(
        select(Alerta).where(
            Alerta.organizacao_id == organizacao_id,
            Alerta.status.in_([StatusAlerta.NOVO, StatusAlerta.EM_ANALISE]),
        )
    ).all()
    agrupado: dict[str, dict[str, Any]] = {}
    for a in alertas:
        if a.cliente_id is None:
            continue
        item = agrupado.setdefault(a.cliente_id, {"score": 0, "alertas": [], "pior": Criticidade.INFO})
        item["score"] += PESO_CRITICIDADE.get(Criticidade(a.criticidade), 1)
        item["alertas"].append({"tipo": a.tipo, "criticidade": a.criticidade, "titulo": a.titulo,
                                "gerado_em": a.gerado_em.isoformat(), "id": a.id})
        if ORDEM_CRITICIDADE[Criticidade(a.criticidade)] > ORDEM_CRITICIDADE[Criticidade(item["pior"])]:
            item["pior"] = a.criticidade

    saida: list[dict[str, Any]] = []
    for cliente_id, dados in agrupado.items():
        cliente = db.get(Cliente, cliente_id)
        if cliente is None:
            continue
        motivos = sorted({a["tipo"] for a in dados["alertas"]})
        saida.append({
            "cliente_id": cliente_id,
            "cnpj": formatar_cnpj(cliente.cnpj),
            "razao_social": cliente.razao_social,
            "responsavel": cliente.responsavel,
            "score": dados["score"],
            "criticidade_maxima": dados["pior"],
            "qtd_alertas": len(dados["alertas"]),
            "motivos": motivos,
            "alertas": sorted(dados["alertas"],
                              key=lambda a: ORDEM_CRITICIDADE[Criticidade(a["criticidade"])],
                              reverse=True)[:5],
            "acao_sugerida": _acao_sugerida(motivos),
        })
    saida.sort(key=lambda x: x["score"], reverse=True)
    return saida[:limite]


def _acao_sugerida(motivos: list[str]) -> str:
    if any("PROCURACAO" in m for m in motivos):
        return "Verificar/renovar procuração no e-CAC antes de novas consultas."
    if any("NAO_HOMOLOGADA" in m or "PERDEU_HOMOLOGACAO" in m for m in motivos):
        return "Conferir despacho decisório e prazo de manifestação no e-CAC."
    if any("EXIGENCIA" in m for m in motivos):
        return "Levantar documentação da intimação e controlar o prazo de resposta."
    if any("NOVO_DEBITO" in m or "PIOROU" in m for m in motivos):
        return "Reconferir situação fiscal e identificar a origem do débito."
    if any("REMANESCENTE" in m for m in motivos):
        return "Revisar vinculação de débitos na PER/DCOMP."
    if any("FONTE" in m or "DESATUALIZADA" in m for m in motivos):
        return "Reexecutar a consulta; se persistir, importar o resultado oficial manualmente."
    return "Revisar o cliente no painel."
