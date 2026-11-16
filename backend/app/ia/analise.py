"""Camada de interpretação (motor de regras explicável).

Limites deliberados desta camada:
 * não cria fato fiscal: só interpreta o que foi consultado e gravado;
 * jamais declara homologação sem evidência da fonte;
 * toda conclusão vem com fonte, data/hora da consulta e campo comparado;
 * não emite parecer jurídico definitivo - sinaliza para validação humana.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.ia.achados import Achado
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao
from app.models.enums import (
    Criticidade,
    Disponibilidade,
    SituacaoCompensacao,
    SituacaoProcuracao,
    TipoAlerta,
)
from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
from app.models.procuracao import Procuracao
from app.services.fiscal import RESSALVA_PADRAO

AVISO_HUMANO = "Conferência humana obrigatória antes de qualquer providência junto ao cliente."


def _brl(valor: Any) -> str:
    try:
        numero = Decimal(str(valor or 0))
    except Exception:  # noqa: BLE001
        return "R$ 0,00"
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _fonte_txt(evidencia: dict[str, Any]) -> str:
    quando = evidencia.get("consultado_em", "?")
    return f"fonte {evidencia.get('fonte', '?')}, consulta de {quando}"


# ------------------------------------------------------------ procurações ---
def analisar_procuracao(
    procuracao: Procuracao, cliente: Cliente, mudanca: dict[str, Any] | None,
    *, hoje: date | None = None,
) -> list[Achado]:
    hoje = hoje or date.today()
    achados: list[Achado] = []
    evidencia = (mudanca or {}).get("evidencia") or {
        "fonte": procuracao.origem_informacao,
        "disponibilidade": procuracao.disponibilidade,
        "consultado_em": procuracao.consultado_em.isoformat() if procuracao.consultado_em else None,
    }
    rotulo = procuracao.numero or procuracao.id[:8]
    nome = cliente.razao_social

    if procuracao.situacao == SituacaoProcuracao.REVOGADA:
        achados.append(Achado(
            tipo=TipoAlerta.PROCURACAO_REVOGADA, criticidade=Criticidade.CRITICA,
            titulo=f"Procuração revogada - {nome}",
            mensagem=f"A procuração {rotulo} consta como REVOGADA. Novas consultas em nome "
                     f"deste cliente deixam de ser autorizadas.",
            explicacao=f"A consulta retornou situação REVOGADA ({_fonte_txt(evidencia)}). "
                       f"{AVISO_HUMANO}",
            dedup_key=f"PROC:{procuracao.id}:REVOGADA",
            cliente_id=cliente.id, entidade="PROCURACAO", entidade_id=procuracao.id,
            evidencias=[evidencia],
        ))
        return achados

    if procuracao.situacao == SituacaoProcuracao.EXPIRADA:
        achados.append(Achado(
            tipo=TipoAlerta.PROCURACAO_EXPIRADA, criticidade=Criticidade.CRITICA,
            titulo=f"Procuração expirada - {nome}",
            mensagem=f"A procuração {rotulo} está expirada"
                     + (f" desde {procuracao.data_fim.strftime('%d/%m/%Y')}" if procuracao.data_fim else "")
                     + ". O monitoramento automático deste cliente fica comprometido.",
            explicacao=f"Situação EXPIRADA confirmada em consulta ({_fonte_txt(evidencia)}). "
                       f"{AVISO_HUMANO}",
            dedup_key=f"PROC:{procuracao.id}:EXPIRADA:{procuracao.data_fim}",
            cliente_id=cliente.id, entidade="PROCURACAO", entidade_id=procuracao.id,
            evidencias=[evidencia],
        ))
        return achados

    if procuracao.data_fim and procuracao.validada_por_fonte:
        dias = (procuracao.data_fim - hoje).days
        faixas = sorted(settings.alerta_procuracao_dias)
        faixa = next((f for f in faixas if dias <= f), None)
        if faixa is not None and dias >= 0:
            criticidade = {0: Criticidade.CRITICA, 7: Criticidade.ALTA,
                           15: Criticidade.MEDIA, 30: Criticidade.BAIXA}.get(faixa, Criticidade.MEDIA)
            quando = "hoje" if dias == 0 else f"em {dias} dia(s)"
            achados.append(Achado(
                tipo=TipoAlerta.PROCURACAO_VENCENDO, criticidade=criticidade,
                titulo=f"Procuração vence {quando} - {nome}",
                mensagem=f"A procuração {rotulo} vence {quando} "
                         f"({procuracao.data_fim.strftime('%d/%m/%Y')}). Renove para não "
                         f"interromper o monitoramento.",
                explicacao=f"Data de validade confirmada pela fonte ({_fonte_txt(evidencia)}); "
                           f"faixa de alerta configurada: {faixa} dia(s).",
                dedup_key=f"PROC:{procuracao.id}:VENCE:{faixa}:{procuracao.data_fim}",
                cliente_id=cliente.id, entidade="PROCURACAO", entidade_id=procuracao.id,
                evidencias=[evidencia],
            ))

    if not procuracao.validada_por_fonte:
        motivo = {
            Disponibilidade.INDISPONIVEL: "a fonte estava indisponível",
            Disponibilidade.NAO_AUTORIZADO: "faltam poderes/credencial para consultar",
            Disponibilidade.SEM_DADOS: "a fonte não localizou a procuração",
            Disponibilidade.NAO_CONSULTADO: "nunca houve consulta automática",
        }.get(procuracao.disponibilidade, "a validação por fonte autorizada não ocorreu")
        achados.append(Achado(
            tipo=TipoAlerta.PROCURACAO_SEM_VALIDACAO, criticidade=Criticidade.MEDIA,
            titulo=f"Procuração sem validação por fonte - {nome}",
            mensagem=f"A procuração {rotulo} está no sistema com situação declarada "
                     f"'{procuracao.situacao_declarada}', mas NÃO foi validada: {motivo}.",
            explicacao="O sistema não presume procuração ativa a partir da planilha. "
                       f"Estado técnico da última consulta: {procuracao.disponibilidade}. "
                       "Enquanto não houver validação, o semáforo permanece CINZA.",
            dedup_key=f"PROC:{procuracao.id}:SEM_VALIDACAO:{procuracao.disponibilidade}",
            cliente_id=cliente.id, entidade="PROCURACAO", entidade_id=procuracao.id,
            evidencias=[evidencia],
        ))
    return achados


# ------------------------------------------------------------ compensações ---
def analisar_compensacao(
    comp: Compensacao, cliente: Cliente, diff: dict[str, Any] | None
) -> list[Achado]:
    achados: list[Achado] = []
    diff = diff or {}
    evidencia = diff.get("evidencia") or {
        "fonte": comp.origem_informacao,
        "disponibilidade": comp.disponibilidade,
        "consultado_em": comp.consultado_em.isoformat() if comp.consultado_em else None,
    }
    anterior = diff.get("situacao_anterior")
    atual = comp.situacao_compensacao
    numero = comp.numero_perdcomp
    nome = cliente.razao_social

    perdeu_homologacao = (
        anterior == SituacaoCompensacao.HOMOLOGADA and atual != SituacaoCompensacao.HOMOLOGADA
    )
    if perdeu_homologacao:
        achados.append(Achado(
            tipo=TipoAlerta.COMPENSACAO_PERDEU_HOMOLOGACAO, criticidade=Criticidade.CRITICA,
            titulo=f"PER/DCOMP deixou de constar como homologada - {nome}",
            mensagem=f"A PER/DCOMP {numero} constava como HOMOLOGADA e passou a constar como "
                     f"{atual}. Verificação imediata recomendada.",
            explicacao=f"Comparação entre a situação gravada na consulta anterior "
                       f"(HOMOLOGADA) e a situação retornada agora ({atual}) - "
                       f"{_fonte_txt(evidencia)}. {AVISO_HUMANO}",
            dedup_key=f"COMP:{comp.id}:PERDEU_HOMOLOGACAO:{atual}",
            cliente_id=cliente.id, entidade="COMPENSACAO", entidade_id=comp.id,
            evidencias=[evidencia, {"campo": "situacao_compensacao", "de": anterior, "para": atual}],
        ))

    if atual == SituacaoCompensacao.NAO_HOMOLOGADA:
        valor = comp.valor_nao_homologado or comp.valor_credito
        achados.append(Achado(
            tipo=TipoAlerta.COMPENSACAO_NAO_HOMOLOGADA, criticidade=Criticidade.CRITICA,
            titulo=f"PER/DCOMP não homologada - {nome}",
            mensagem=f"A PER/DCOMP {numero} consta como NÃO HOMOLOGADA"
                     + (f" (valor envolvido: {_brl(valor)})" if valor else "")
                     + (f". Despacho decisório {comp.numero_despacho}." if comp.numero_despacho else "."),
            explicacao=f"Situação retornada pela fonte: NAO_HOMOLOGADA ({_fonte_txt(evidencia)}). "
                       f"Há despacho decisório: {comp.tem_despacho_decisorio}. "
                       f"O sistema não avalia mérito nem prazo recursal. {AVISO_HUMANO}",
            dedup_key=f"COMP:{comp.id}:NAO_HOMOLOGADA",
            cliente_id=cliente.id, entidade="COMPENSACAO", entidade_id=comp.id,
            evidencias=[evidencia],
        ))
    elif atual == SituacaoCompensacao.COM_EXIGENCIA:
        prazo = comp.prazo_resposta_intimacao
        achados.append(Achado(
            tipo=TipoAlerta.COMPENSACAO_COM_EXIGENCIA, criticidade=Criticidade.ALTA,
            titulo=f"PER/DCOMP com exigência/intimação - {nome}",
            mensagem=f"A PER/DCOMP {numero} está com exigência ou intimação"
                     + (f", prazo de resposta até {prazo.strftime('%d/%m/%Y')}" if prazo else "")
                     + ".",
            explicacao=f"Situação retornada: COM_EXIGENCIA; indicador de intimação="
                       f"{comp.tem_intimacao} ({_fonte_txt(evidencia)}).",
            dedup_key=f"COMP:{comp.id}:COM_EXIGENCIA:{prazo}",
            cliente_id=cliente.id, entidade="COMPENSACAO", entidade_id=comp.id,
            evidencias=[evidencia],
        ))
    elif atual == SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE:
        achados.append(Achado(
            tipo=TipoAlerta.COMPENSACAO_MUDANCA_SITUACAO, criticidade=Criticidade.ALTA,
            titulo=f"PER/DCOMP homologada parcialmente - {nome}",
            mensagem=f"A PER/DCOMP {numero} foi homologada parcialmente"
                     + (f"; valor não homologado: {_brl(comp.valor_nao_homologado)}"
                        if comp.valor_nao_homologado else "")
                     + ".",
            explicacao=f"Situação retornada: HOMOLOGADA_PARCIALMENTE ({_fonte_txt(evidencia)}). "
                       "O saldo não homologado pode gerar débito em cobrança.",
            dedup_key=f"COMP:{comp.id}:PARCIAL:{comp.valor_nao_homologado}",
            cliente_id=cliente.id, entidade="COMPENSACAO", entidade_id=comp.id,
            evidencias=[evidencia],
        ))
    elif diff.get("mudou_situacao") and not perdeu_homologacao:
        achados.append(Achado(
            tipo=TipoAlerta.COMPENSACAO_MUDANCA_SITUACAO, criticidade=Criticidade.MEDIA,
            titulo=f"Mudança de situação na PER/DCOMP {numero} - {nome}",
            mensagem=f"A situação mudou de {anterior} para {atual}.",
            explicacao=f"Diferença entre a última situação gravada e a retornada agora "
                       f"({_fonte_txt(evidencia)}). Transmissão não equivale a homologação.",
            dedup_key=f"COMP:{comp.id}:MUDANCA:{anterior}->{atual}",
            cliente_id=cliente.id, entidade="COMPENSACAO", entidade_id=comp.id,
            evidencias=[evidencia, {"campo": "situacao_compensacao", "de": anterior, "para": atual}],
        ))

    if diff.get("disponibilidade") in (Disponibilidade.INDISPONIVEL, Disponibilidade.NAO_AUTORIZADO):
        achados.append(Achado(
            tipo=TipoAlerta.FONTE_INDISPONIVEL, criticidade=Criticidade.MEDIA,
            titulo=f"Consulta de PER/DCOMP sem resultado - {nome}",
            mensagem=f"Não foi possível atualizar a PER/DCOMP {numero}: "
                     f"{diff.get('disponibilidade')}. A informação em tela é a da consulta anterior.",
            explicacao="Falha de consulta NÃO significa ausência de pendência; a situação "
                       f"anterior ({atual}) foi preservada e marcada como desatualizada. "
                       f"Mensagem da fonte: {evidencia.get('mensagem', 'n/d')}.",
            dedup_key=f"COMP:{comp.id}:FONTE:{diff.get('disponibilidade')}:{date.today()}",
            cliente_id=cliente.id, entidade="COMPENSACAO", entidade_id=comp.id,
            evidencias=[evidencia],
        ))
    return achados


# --------------------------------------------------------- situação fiscal ---
def analisar_situacao_fiscal(
    cliente: Cliente, snapshot: SituacaoFiscalSnapshot,
    comparativo: SituacaoFiscalComparativo | None,
    *, compensacoes_recentes: list[Compensacao] | None = None,
) -> list[Achado]:
    achados: list[Achado] = []
    nome = cliente.razao_social
    evidencia = {
        "fonte": snapshot.origem,
        "disponibilidade": snapshot.disponibilidade,
        "consultado_em": snapshot.consultado_em.isoformat(),
        "entidade": "SITUACAO_FISCAL",
        "entidade_id": snapshot.id,
        "hash_conteudo": snapshot.hash_conteudo,
    }

    if snapshot.disponibilidade in (Disponibilidade.INDISPONIVEL, Disponibilidade.NAO_AUTORIZADO):
        achados.append(Achado(
            tipo=TipoAlerta.FONTE_INDISPONIVEL, criticidade=Criticidade.MEDIA,
            titulo=f"Situação fiscal não pôde ser consultada - {nome}",
            mensagem=f"A consulta retornou {snapshot.disponibilidade}: {snapshot.mensagem or 'sem detalhe'}.",
            explicacao="Resultado técnico de indisponibilidade. O sistema NÃO conclui que o "
                       "cliente está regular; a situação permanece como 'não atualizada'.",
            dedup_key=f"FISCAL:{cliente.id}:FONTE:{snapshot.disponibilidade}:{date.today()}",
            cliente_id=cliente.id, entidade="SITUACAO_FISCAL", entidade_id=snapshot.id,
            evidencias=[evidencia],
        ))
        return achados

    if comparativo is not None:
        if comparativo.novos:
            total_novos = sum(Decimal(str(p.get("valor") or 0)) for p in comparativo.novos)
            descricoes = "; ".join(
                f"{p.get('codigo') or p.get('categoria')} {p.get('periodo') or ''} "
                f"({_brl(p.get('valor'))})" for p in comparativo.novos[:5]
            )
            achados.append(Achado(
                tipo=TipoAlerta.SITUACAO_FISCAL_NOVO_DEBITO, criticidade=Criticidade.ALTA,
                titulo=f"{len(comparativo.novos)} novo(s) débito/pendência - {nome}",
                mensagem=f"Surgiram {len(comparativo.novos)} pendência(s) não presentes na consulta "
                         f"anterior, somando {_brl(total_novos)}: {descricoes}.",
                explicacao="Comparação entre as chaves de pendência do snapshot anterior e do atual. "
                           f"{_fonte_txt(evidencia)}. {RESSALVA_PADRAO}",
                dedup_key=f"FISCAL:{cliente.id}:NOVOS:{snapshot.hash_conteudo}",
                cliente_id=cliente.id, entidade="SITUACAO_FISCAL", entidade_id=snapshot.id,
                evidencias=[evidencia, {"campo": "novos", "quantidade": len(comparativo.novos),
                                        "itens": comparativo.novos[:10]}],
            ))
        diferenca = Decimal(str(comparativo.diferenca))
        if diferenca > 0 and not comparativo.novos:
            achados.append(Achado(
                tipo=TipoAlerta.SITUACAO_FISCAL_PIOROU, criticidade=Criticidade.ALTA,
                titulo=f"Aumento de débitos - {nome}",
                mensagem=f"O total de débitos passou de {_brl(comparativo.total_anterior)} para "
                         f"{_brl(comparativo.total_atual)} (variação de {_brl(diferenca)}).",
                explicacao=f"Diferença aritmética entre dois snapshots ({_fonte_txt(evidencia)}). "
                           f"{RESSALVA_PADRAO}",
                dedup_key=f"FISCAL:{cliente.id}:PIOROU:{snapshot.hash_conteudo}",
                cliente_id=cliente.id, entidade="SITUACAO_FISCAL", entidade_id=snapshot.id,
                evidencias=[evidencia, {"campo": "total_debitos",
                                        "de": str(comparativo.total_anterior),
                                        "para": str(comparativo.total_atual)}],
            ))
        if diferenca < 0:
            achados.append(Achado(
                tipo=TipoAlerta.SITUACAO_FISCAL_MELHOROU, criticidade=Criticidade.INFO,
                titulo=f"Redução de débitos - {nome}",
                mensagem=f"O total de débitos caiu de {_brl(comparativo.total_anterior)} para "
                         f"{_brl(comparativo.total_atual)} (redução de {_brl(abs(diferenca))}).",
                explicacao=f"Diferença aritmética entre dois snapshots ({_fonte_txt(evidencia)}). "
                           f"{RESSALVA_PADRAO}",
                dedup_key=f"FISCAL:{cliente.id}:MELHOROU:{snapshot.hash_conteudo}",
                cliente_id=cliente.id, entidade="SITUACAO_FISCAL", entidade_id=snapshot.id,
                evidencias=[evidencia, {"campo": "total_debitos",
                                        "de": str(comparativo.total_anterior),
                                        "para": str(comparativo.total_atual),
                                        "baixados": comparativo.baixados[:10]}],
            ))
        if comparativo.permanecem and compensacoes_recentes:
            homologadas = [c for c in compensacoes_recentes
                           if c.situacao_compensacao in (SituacaoCompensacao.HOMOLOGADA,
                                                         SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE)]
            if homologadas:
                total_rem = sum(Decimal(str(p.get("valor") or 0)) for p in comparativo.permanecem)
                achados.append(Achado(
                    tipo=TipoAlerta.SITUACAO_FISCAL_DEBITO_REMANESCENTE, criticidade=Criticidade.MEDIA,
                    titulo=f"Débitos remanescentes após compensação - {nome}",
                    mensagem=f"{len(comparativo.permanecem)} pendência(s) permanecem após "
                             f"{len(homologadas)} compensação(ões) com homologação registrada "
                             f"(total remanescente {_brl(total_rem)}).",
                    explicacao="Cruzamento entre pendências que se repetem nos dois snapshots e "
                               "PER/DCOMPs com situação homologada/parcial registrada pela fonte. "
                               "O sistema não afirma que estas pendências deveriam ter sido "
                               f"extintas pela compensação. {AVISO_HUMANO}",
                    dedup_key=f"FISCAL:{cliente.id}:REMANESCENTE:{snapshot.hash_conteudo}",
                    cliente_id=cliente.id, entidade="SITUACAO_FISCAL", entidade_id=snapshot.id,
                    evidencias=[evidencia,
                                {"campo": "permanecem", "itens": comparativo.permanecem[:10]},
                                {"campo": "perdcomps_homologadas",
                                 "itens": [c.numero_perdcomp for c in homologadas][:10]}],
                ))
    return achados


# ---------------------------------------------------------------- frescor ---
def analisar_frescor(cliente: Cliente, *, agora: datetime | None = None) -> list[Achado]:
    agora = agora or datetime.now(UTC)
    limite = settings.consulta_desatualizada_dias
    pendentes: list[str] = []
    detalhes: list[dict[str, Any]] = []
    for rotulo, campo in (("procurações", "ultima_consulta_procuracao"),
                          ("PER/DCOMP", "ultima_consulta_compensacao"),
                          ("situação fiscal", "ultima_consulta_fiscal")):
        valor = getattr(cliente, campo)
        if valor is None:
            pendentes.append(f"{rotulo}: nunca consultado")
            detalhes.append({"dominio": rotulo, "ultima_consulta": None})
            continue
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=UTC)
        dias = (agora - valor).days
        if dias > limite:
            pendentes.append(f"{rotulo}: há {dias} dia(s)")
            detalhes.append({"dominio": rotulo, "ultima_consulta": valor.isoformat(), "dias": dias})
    if not pendentes:
        return []
    return [Achado(
        tipo=TipoAlerta.CONSULTA_DESATUALIZADA,
        criticidade=Criticidade.BAIXA if len(pendentes) == 1 else Criticidade.MEDIA,
        titulo=f"Informação desatualizada - {cliente.razao_social}",
        mensagem="Sem consulta atualizada para: " + "; ".join(pendentes) + ".",
        explicacao=f"Limite configurado: {limite} dia(s) (MT_CONSULTA_DESATUALIZADA_DIAS). "
                   "Informação desatualizada não é o mesmo que ausência de pendência.",
        dedup_key=f"FRESCOR:{cliente.id}:{agora.date()}",
        cliente_id=cliente.id, entidade="CLIENTE", entidade_id=cliente.id,
        evidencias=[{"fonte": "SISTEMA", "consultado_em": agora.isoformat(), "detalhes": detalhes}],
    )]
