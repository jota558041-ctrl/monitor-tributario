"""Testes das regras inegociáveis do projeto."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.connectors.base import ResultadoConsulta
from app.ia import analise
from app.models.enums import (
    Disponibilidade,
    OrigemInformacao,
    Semaforo,
    SituacaoCompensacao,
    SituacaoFiscalGeral,
    SituacaoProcuracao,
    TipoAlerta,
)
from app.services import compensacoes as svc_comp
from app.services import fiscal as svc_fiscal
from app.services import procuracoes as svc_proc


def _resultado(dados, disponibilidade=Disponibilidade.OK, origem=OrigemInformacao.SIMULADOR):
    return ResultadoConsulta(
        disponibilidade=disponibilidade, origem=origem,
        fonte_descricao="fonte de teste", dados=dados,
    )


# --------------------------------------------------- procurações: não presumir
def test_procuracao_da_planilha_nao_e_considerada_ativa(db, cliente):
    proc, criada = svc_proc.upsert_procuracao(
        db, cliente, {"numero": "P-1", "data_fim": (date.today() + timedelta(days=200)).isoformat()},
        origem=OrigemInformacao.PLANILHA,
    )
    assert criada
    assert proc.situacao == SituacaoProcuracao.DESCONHECIDA
    assert proc.situacao_declarada == SituacaoProcuracao.ATIVA   # o que a planilha diz
    assert proc.validada_por_fonte is False
    assert svc_proc.semaforo(proc) == Semaforo.CINZA


def test_procuracao_fica_ativa_somente_apos_validacao_por_fonte(db, cliente):
    proc, _ = svc_proc.upsert_procuracao(db, cliente, {"numero": "P-2"})
    data_fim = date.today() + timedelta(days=100)
    svc_proc.registrar_consulta(db, proc, _resultado(
        {"situacao": "ATIVA", "data_fim": data_fim.isoformat()}
    ))
    assert proc.validada_por_fonte is True
    assert proc.situacao == SituacaoProcuracao.ATIVA
    assert svc_proc.semaforo(proc) == Semaforo.VERDE


def test_semaforo_amarelo_quando_proxima_do_vencimento(db, cliente):
    proc, _ = svc_proc.upsert_procuracao(db, cliente, {"numero": "P-3"})
    svc_proc.registrar_consulta(db, proc, _resultado(
        {"situacao": "ATIVA", "data_fim": (date.today() + timedelta(days=9)).isoformat()}
    ))
    assert proc.situacao == SituacaoProcuracao.PROXIMA_VENCIMENTO
    assert svc_proc.semaforo(proc) == Semaforo.AMARELO


def test_consulta_indisponivel_nao_mantem_procuracao_como_ativa(db, cliente):
    proc, _ = svc_proc.upsert_procuracao(db, cliente, {"numero": "P-4"})
    svc_proc.registrar_consulta(db, proc, _resultado(
        {"situacao": "ATIVA", "data_fim": (date.today() + timedelta(days=300)).isoformat()}
    ))
    assert proc.situacao == SituacaoProcuracao.ATIVA
    svc_proc.registrar_consulta(db, proc, _resultado(None, Disponibilidade.INDISPONIVEL))
    assert proc.situacao == SituacaoProcuracao.DESCONHECIDA
    assert svc_proc.semaforo(proc) == Semaforo.CINZA
    assert len(proc.consultas) == 2      # histórico preservado


def test_alerta_de_procuracao_vencendo_tem_evidencia_e_faixa(db, cliente):
    proc, _ = svc_proc.upsert_procuracao(db, cliente, {"numero": "P-5"})
    diff = svc_proc.registrar_consulta(db, proc, _resultado(
        {"situacao": "ATIVA", "data_fim": (date.today() + timedelta(days=5)).isoformat()}
    ))
    achados = analise.analisar_procuracao(proc, cliente, diff)
    tipos = {a.tipo for a in achados}
    assert TipoAlerta.PROCURACAO_VENCENDO in tipos
    alerta = next(a for a in achados if a.tipo == TipoAlerta.PROCURACAO_VENCENDO)
    assert alerta.evidencias and "consultado_em" in alerta.evidencias[0]
    assert "faixa de alerta" in alerta.explicacao


# ------------------------------------------- compensações: transmissão != homologação
def test_transmissao_nao_vira_homologacao(db, cliente):
    comp, _ = svc_comp.upsert_compensacao(db, cliente, {
        "numero_perdcomp": "PD-1", "valor_credito": "1000",
        "situacao_compensacao": SituacaoCompensacao.TRANSMITIDA,
    })
    assert comp.situacao_compensacao == SituacaoCompensacao.TRANSMITIDA
    achados = analise.analisar_compensacao(comp, cliente, {})
    assert not any(a.tipo == TipoAlerta.COMPENSACAO_NAO_HOMOLOGADA for a in achados)


def test_sem_situacao_informada_fica_sem_informacao(db, cliente):
    comp, _ = svc_comp.upsert_compensacao(db, cliente, {"numero_perdcomp": "PD-2"})
    assert comp.situacao_compensacao == SituacaoCompensacao.SEM_INFORMACAO


def test_mudanca_de_situacao_gera_evento_e_alerta(db, cliente):
    comp, _ = svc_comp.upsert_compensacao(db, cliente, {
        "numero_perdcomp": "PD-3", "valor_credito": "5000",
        "situacao_compensacao": SituacaoCompensacao.EM_ANALISE,
    })
    diff = svc_comp.registrar_consulta(db, comp, _resultado({
        "situacao_compensacao": "NAO_HOMOLOGADA", "valor_nao_homologado": "5000",
        "tem_despacho_decisorio": True, "numero_despacho": "DD-1",
    }))
    assert diff["mudou_situacao"] is True
    assert comp.situacao_compensacao == SituacaoCompensacao.NAO_HOMOLOGADA
    assert len(comp.eventos) == 2        # cadastro + mudança
    achados = analise.analisar_compensacao(comp, cliente, diff)
    assert any(a.tipo == TipoAlerta.COMPENSACAO_NAO_HOMOLOGADA for a in achados)


def test_perda_de_homologacao_gera_alerta_critico(db, cliente):
    comp, _ = svc_comp.upsert_compensacao(db, cliente, {
        "numero_perdcomp": "PD-4", "valor_credito": "9000",
        "situacao_compensacao": SituacaoCompensacao.HOMOLOGADA,
    })
    diff = svc_comp.registrar_consulta(db, comp, _resultado(
        {"situacao_compensacao": "EM_ANALISE"}
    ))
    achados = analise.analisar_compensacao(comp, cliente, diff)
    alerta = next(a for a in achados if a.tipo == TipoAlerta.COMPENSACAO_PERDEU_HOMOLOGACAO)
    assert alerta.criticidade == "CRITICA"
    assert any(e.get("de") == "HOMOLOGADA" for e in alerta.evidencias)


def test_falha_de_consulta_preserva_situacao_conhecida(db, cliente):
    comp, _ = svc_comp.upsert_compensacao(db, cliente, {
        "numero_perdcomp": "PD-5", "situacao_compensacao": SituacaoCompensacao.HOMOLOGADA,
    })
    diff = svc_comp.registrar_consulta(db, comp, _resultado(None, Disponibilidade.INDISPONIVEL))
    assert comp.situacao_compensacao == SituacaoCompensacao.HOMOLOGADA   # não rebaixa
    assert comp.disponibilidade == Disponibilidade.INDISPONIVEL
    achados = analise.analisar_compensacao(comp, cliente, diff)
    assert any(a.tipo == TipoAlerta.FONTE_INDISPONIVEL for a in achados)


# ---------------------------------------------------- situação fiscal: comparação
def _pendencia(codigo, valor, categoria="DEBITO_FEDERAL", periodo="01/2024"):
    return {"categoria": categoria, "codigo": codigo, "descricao": f"Débito {codigo}",
            "periodo": periodo, "valor": valor, "situacao": "DEVEDOR"}


def test_comparativo_identifica_novos_baixados_e_remanescentes(db, cliente):
    s1 = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS",
        "pendencias": [_pendencia("A", "10000.00"), _pendencia("B", "5000.00")],
    }))
    s2 = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS",
        "pendencias": [_pendencia("B", "5000.00"), _pendencia("C", "2000.00")],
    }))
    comp = svc_fiscal.comparar(db, cliente, s1, s2)
    assert Decimal(str(s1.total_debitos)) == Decimal("15000.00")
    assert Decimal(str(s2.total_debitos)) == Decimal("7000.00")
    assert Decimal(str(comp.diferenca)) == Decimal("-8000.00")
    assert [p["codigo"] for p in comp.novos] == ["C"]
    assert [p["codigo"] for p in comp.baixados] == ["A"]
    assert [p["codigo"] for p in comp.permanecem] == ["B"]
    assert "NÃO implica relação de causa e efeito" in comp.ressalva


def test_cenario_do_enunciado_15k_para_5k(db, cliente):
    s1 = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS", "pendencias": [_pendencia("X", "15000.00")],
    }))
    s2 = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS", "pendencias": [_pendencia("X", "5000.00")],
    }))
    comp = svc_fiscal.comparar(db, cliente, s1, s2)
    assert Decimal(str(comp.diferenca)) == Decimal("-10000.00")
    assert comp.alterados[0]["variacao"] == "-10000.00"
    achados = analise.analisar_situacao_fiscal(cliente, s2, comp)
    melhora = next(a for a in achados if a.tipo == TipoAlerta.SITUACAO_FISCAL_MELHOROU)
    assert "NÃO implica relação de causa e efeito" in melhora.explicacao


def test_debitos_suspensos_e_parcelamentos_nao_entram_no_total_exigivel(db, cliente):
    snap = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS",
        "pendencias": [
            _pendencia("D1", "1000.00"),
            _pendencia("S1", "50000.00", categoria="DEBITO_SUSPENSO"),
            _pendencia("P1", "30000.00", categoria="PARCELAMENTO"),
        ],
    }))
    assert Decimal(str(snap.total_debitos)) == Decimal("1000.00")
    assert Decimal(str(snap.total_suspenso)) == Decimal("50000.00")
    assert Decimal(str(snap.total_parcelado)) == Decimal("30000.00")


def test_indisponibilidade_nao_e_regularidade(db, cliente):
    snap = svc_fiscal.criar_snapshot(
        db, cliente, _resultado(None, Disponibilidade.INDISPONIVEL)
    )
    assert snap.situacao_geral == SituacaoFiscalGeral.INDISPONIVEL
    assert snap.situacao_geral != SituacaoFiscalGeral.REGULAR
    achados = analise.analisar_situacao_fiscal(cliente, snap, None)
    alerta = next(a for a in achados if a.tipo == TipoAlerta.FONTE_INDISPONIVEL)
    assert "NÃO conclui que o cliente está regular" in alerta.explicacao


def test_nao_autorizado_tambem_nao_e_regularidade(db, cliente):
    snap = svc_fiscal.criar_snapshot(
        db, cliente, _resultado(None, Disponibilidade.NAO_AUTORIZADO)
    )
    assert snap.situacao_geral == SituacaoFiscalGeral.INDISPONIVEL


def test_debito_remanescente_apos_homologacao(db, cliente):
    comp, _ = svc_comp.upsert_compensacao(db, cliente, {
        "numero_perdcomp": "PD-R", "valor_credito": "1000",
        "situacao_compensacao": SituacaoCompensacao.HOMOLOGADA,
    })
    s1 = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS", "pendencias": [_pendencia("R1", "7000.00")]}))
    s2 = svc_fiscal.criar_snapshot(db, cliente, _resultado({
        "situacao_geral": "COM_PENDENCIAS", "pendencias": [_pendencia("R1", "7000.00")]}))
    comparativo = svc_fiscal.comparar(db, cliente, s1, s2)
    achados = analise.analisar_situacao_fiscal(
        cliente, s2, comparativo, compensacoes_recentes=[comp]
    )
    alerta = next(a for a in achados
                  if a.tipo == TipoAlerta.SITUACAO_FISCAL_DEBITO_REMANESCENTE)
    assert "não afirma" in alerta.explicacao
    assert any(e.get("campo") == "perdcomps_homologadas" for e in alerta.evidencias)


def test_frescor_detecta_nunca_consultado(db, cliente):
    achados = analise.analisar_frescor(cliente)
    assert achados and achados[0].tipo == TipoAlerta.CONSULTA_DESATUALIZADA
    assert "nunca consultado" in achados[0].mensagem


def test_deduplicacao_de_alertas(db, cliente, organizacao):
    from app.services import alertas as svc_alertas

    achados = analise.analisar_frescor(cliente)
    r1 = svc_alertas.registrar_achados(db, organizacao.id, achados)
    r2 = svc_alertas.registrar_achados(db, organizacao.id, achados)
    assert r1["criados"] == 1
    assert r2["criados"] == 0 and r2["repetidos"] == 1
