"""Geração de planilhas: modelo de importação e massa de teste."""
from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

COLUNAS_MODELO = [
    "CNPJ", "Razão Social", "Nome Fantasia", "E-mail", "Responsável pelo cliente",
    "Número da Procuração", "Data de Validade da Procuração", "Tributos Trabalhados",
    "Número da PER/DCOMP", "Valor da Compensação", "Data da Operação",
    "Período de Apuração", "Situação da Compensação",
]

AZUL_MARINHO = "1B2A4A"
AZUL_CLARO = "DCE6F5"


def _estilizar(ws, colunas: list[str]) -> None:
    for idx, nome in enumerate(colunas, start=1):
        celula = ws.cell(row=1, column=idx, value=nome)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=AZUL_MARINHO)
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(idx)].width = max(16, min(34, len(nome) + 6))
    ws.freeze_panes = "A2"


def gerar_modelo() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Clientes"
    _estilizar(ws, COLUNAS_MODELO)
    exemplos = [
        ["11222333000181", "Exemplo Indústria Ltda", "Exemplo", "fiscal@exemplo.com.br",
         "Ana Souza", "PROC-2025-0001", (date.today() + timedelta(days=200)).strftime("%d/%m/%Y"),
         "PIS/COFINS", "41234.56789.010125.1.3.04-1234", "125000,00",
         (date.today() - timedelta(days=90)).strftime("%d/%m/%Y"), "01/2024", "Transmitida"],
        ["11222333000181", "Exemplo Indústria Ltda", "Exemplo", "fiscal@exemplo.com.br",
         "Ana Souza", "PROC-2025-0001", (date.today() + timedelta(days=200)).strftime("%d/%m/%Y"),
         "IRPJ", "41234.56789.020125.1.3.04-5678", "48000,00",
         (date.today() - timedelta(days=60)).strftime("%d/%m/%Y"), "02/2024", ""],
    ]
    for linha in exemplos:
        ws.append(linha)

    ajuda = wb.create_sheet("Instruções")
    ajuda.column_dimensions["A"].width = 120
    textos = [
        "MONITOR TRIBUTÁRIO - modelo de importação",
        "",
        "1. Apenas 'CNPJ' é obrigatório; as demais colunas são opcionais.",
        "2. O sistema reconhece variações de nome de coluna (ex.: 'CNPJ do contribuinte').",
        "3. Um mesmo CNPJ pode aparecer em várias linhas: cada linha pode trazer uma PER/DCOMP.",
        "4. Datas aceitas: dd/mm/aaaa, aaaa-mm-dd ou data nativa do Excel.",
        "5. Valores aceitos: 1.234,56 / 1234.56 / R$ 1.234,56.",
        "6. 'Situação da Compensação' é apenas o que a empresa declara; o sistema só considera",
        "   homologação quando houver evidência de consulta à fonte oficial.",
        "7. A validade da procuração informada aqui NÃO é tratada como situação confirmada:",
        "   o semáforo fica CINZA até a validação por fonte autorizada.",
        "8. Linhas com CNPJ inválido ficam bloqueadas para correção antes da importação.",
    ]
    for i, texto in enumerate(textos, start=1):
        celula = ajuda.cell(row=i, column=1, value=texto)
        if i == 1:
            celula.font = Font(bold=True, size=14, color=AZUL_MARINHO)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def gerar_planilha(linhas: list[dict[str, Any]], *, titulo: str = "Clientes") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = titulo
    _estilizar(ws, COLUNAS_MODELO)
    chaves = ["cnpj", "razao_social", "nome_fantasia", "email", "responsavel",
              "numero_procuracao", "validade_procuracao", "tributos_trabalhados",
              "numero_perdcomp", "valor_compensacao", "data_operacao",
              "periodo_apuracao", "situacao_compensacao"]
    for linha in linhas:
        ws.append([linha.get(chave, "") for chave in chaves])
    for col in ("A",):
        for celula in ws[col][1:]:
            celula.alignment = Alignment(horizontal="left")
            celula.number_format = "@"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def gerar_csv(linhas: list[dict[str, Any]]) -> bytes:
    import csv

    chaves = ["cnpj", "razao_social", "nome_fantasia", "email", "responsavel",
              "numero_procuracao", "validade_procuracao", "tributos_trabalhados",
              "numero_perdcomp", "valor_compensacao", "data_operacao",
              "periodo_apuracao", "situacao_compensacao"]
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(COLUNAS_MODELO)
    for linha in linhas:
        escritor.writerow([linha.get(chave, "") for chave in chaves])
    return buffer.getvalue().encode("utf-8-sig")
