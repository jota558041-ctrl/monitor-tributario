"""Validações de domínio: CNPJ, parsers e detecção de colunas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.cnpj import cnpj_valido, cpf_valido, gerar_cnpj_valido
from app.services.importacao import detectar_colunas, normalizar_situacao_texto
from app.services.parsers import parse_data, parse_decimal, parse_periodo


@pytest.mark.parametrize("cnpj,esperado", [
    ("11.222.333/0001-81", True),
    ("11222333000181", True),
    ("11222333000182", False),      # DV incorreto
    ("00000000000000", False),      # repetidos
    ("1122233300018", False),       # 13 dígitos
    ("", False),
])
def test_cnpj(cnpj, esperado):
    assert cnpj_valido(cnpj) is esperado


def test_cnpj_gerado_e_valido():
    for base in (1, 99, 12345678, 87654321):
        assert cnpj_valido(gerar_cnpj_valido(base))


def test_cpf():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("111.111.111-11")


@pytest.mark.parametrize("entrada,esperado", [
    ("R$ 1.234,56", Decimal("1234.56")),
    ("1.234,56", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")),
    ("1234.56", Decimal("1234.56")),
    ("(500,00)", Decimal("-500.00")),
    ("", None),
    (None, None),
])
def test_parse_decimal(entrada, esperado):
    assert parse_decimal(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("31/12/2026", date(2026, 12, 31)),
    ("2026-01-05", date(2026, 1, 5)),
    ("05.01.2026", date(2026, 1, 5)),
    ("texto", None),
])
def test_parse_data(entrada, esperado):
    assert parse_data(entrada) == esperado


def test_parse_periodo():
    assert parse_periodo("3/2025") == "03/2025"
    assert parse_periodo("2025-03-01") == "03/2025"
    assert parse_periodo("2024") == "2024"


def test_deteccao_colunas_da_planilha_do_cliente():
    colunas = ["CNPJ", "Razão social", "Nome fantasia", "E-mail",
               "Responsável pelo cliente", "Número da procuração",
               "Data de validade da procuração", "Tributos trabalhados",
               "Número da PER/DCOMP", "Valor da compensação", "Data da operação"]
    mapeamento, ignoradas = detectar_colunas(colunas)
    assert mapeamento["CNPJ"] == "cnpj"
    assert mapeamento["Responsável pelo cliente"] == "responsavel"
    assert mapeamento["Data de validade da procuração"] == "validade_procuracao"
    assert mapeamento["Número da PER/DCOMP"] == "numero_perdcomp"
    assert mapeamento["Valor da compensação"] == "valor_compensacao"
    assert ignoradas == []


def test_deteccao_colunas_com_variacoes_e_desconhecidas():
    mapeamento, ignoradas = detectar_colunas(
        ["cnpj do contribuinte", "empresa", "vencimento procuracao", "perdcomp", "Coluna X"]
    )
    assert mapeamento["cnpj do contribuinte"] == "cnpj"
    assert mapeamento["empresa"] == "razao_social"
    assert mapeamento["vencimento procuracao"] == "validade_procuracao"
    assert mapeamento["perdcomp"] == "numero_perdcomp"
    assert ignoradas == ["Coluna X"]


def test_normalizacao_situacao():
    assert str(normalizar_situacao_texto("Homologada")) == "HOMOLOGADA"
    assert str(normalizar_situacao_texto("deferida parcialmente")) == "HOMOLOGADA_PARCIALMENTE"
    assert normalizar_situacao_texto("blablabla") is None
