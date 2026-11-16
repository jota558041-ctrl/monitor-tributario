"""Massa de dados fictícia: 10 empresas demonstrativas.

Os CNPJs são matematicamente válidos (dígitos verificadores corretos), mas
inventados. Nenhum dado real é utilizado.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.services.cnpj import formatar_cnpj, gerar_cnpj_valido

HOJE = date.today()


def _d(dias: int) -> str:
    return (HOJE + timedelta(days=dias)).strftime("%d/%m/%Y")


# (nome, fantasia, responsavel, tributos, dias_validade_procuracao, cenario_fiscal)
EMPRESAS: list[dict[str, Any]] = [
    {"base": 10000001, "razao_social": "Alfa Indústria de Alimentos Ltda", "fantasia": "Alfa Alimentos",
     "responsavel": "Ana Souza", "tributos": "PIS/COFINS", "validade": 320,
     "perfil": "REGULAR_HOMOLOGADA",
     "perdcomps": [("41234.56789.010125.1.3.04-1001", "PIS", "01/2024", "185000,00", -210, "Transmitida"),
                   ("41234.56789.020125.1.3.04-1002", "COFINS", "02/2024", "92500,00", -180, "")]},
    {"base": 10000002, "razao_social": "Beta Comércio de Peças S.A.", "fantasia": "Beta Peças",
     "responsavel": "Bruno Lima", "tributos": "IRPJ/CSLL", "validade": 25,
     "perfil": "COM_DEBITOS",
     "perdcomps": [("41234.56789.030125.1.3.04-2001", "IRPJ", "03/2024", "64000,00", -150, "Em análise")]},
    {"base": 10000003, "razao_social": "Gama Transportes Rodoviários Ltda", "fantasia": "Gama Log",
     "responsavel": "Carla Dias", "tributos": "Contribuição Previdenciária", "validade": -15,
     "perfil": "PROCURACAO_VENCIDA",
     "perdcomps": [("41234.56789.040125.1.3.04-3001", "CPP", "04/2024", "47300,00", -120, "Transmitida")]},
    {"base": 10000004, "razao_social": "Delta Serviços de Engenharia Ltda", "fantasia": "Delta Eng",
     "responsavel": "Bruno Lima", "tributos": "ISS/IRPJ", "validade": 180,
     "perfil": "PROCURACAO_REVOGADA",
     "perdcomps": [("41234.56789.050125.1.3.04-4001", "IRPJ", "05/2024", "28900,00", -100, "")]},
    {"base": 10000005, "razao_social": "Épsilon Varejo e Distribuição Ltda", "fantasia": "Épsilon Varejo",
     "responsavel": "Ana Souza", "tributos": "PIS/COFINS", "validade": 95,
     "perfil": "FONTE_INDISPONIVEL",
     "perdcomps": [("41234.56789.060125.1.3.04-5001", "COFINS", "06/2024", "156400,00", -95, "Transmitida")]},
    {"base": 10000006, "razao_social": "Zeta Agropecuária Ltda", "fantasia": "Zeta Agro",
     "responsavel": "Carla Dias", "tributos": "FUNRURAL", "validade": 60,
     "perfil": "SEM_PODERES",
     "perdcomps": [("41234.56789.070125.1.3.04-6001", "FUNRURAL", "07/2024", "73200,00", -85, "")]},
    {"base": 10000007, "razao_social": "Eta Metalúrgica do Brasil Ltda", "fantasia": "Eta Metal",
     "responsavel": "Daniel Rocha", "tributos": "IPI/PIS/COFINS", "validade": 240,
     "perfil": "NAO_HOMOLOGADA",
     "perdcomps": [("41234.56789.080125.1.3.04-7001", "IPI", "08/2024", "310000,00", -260, "Transmitida"),
                   ("41234.56789.090125.1.3.04-7002", "PIS", "09/2024", "58000,00", -230, "Em análise")]},
    {"base": 10000008, "razao_social": "Teta Tecnologia e Sistemas Ltda", "fantasia": "Teta Tech",
     "responsavel": "Daniel Rocha", "tributos": "CSLL", "validade": 12,
     "perfil": "COM_EXIGENCIA",
     "perdcomps": [("41234.56789.100125.1.3.04-8001", "CSLL", "10/2024", "41500,00", -75, "Transmitida")]},
    {"base": 10000009, "razao_social": "Iota Construtora e Incorporadora Ltda", "fantasia": "Iota Obras",
     "responsavel": "Ana Souza", "tributos": "CPRB/IRPJ", "validade": 400,
     "perfil": "PARCELAMENTO",
     "perdcomps": [("41234.56789.110125.1.3.04-9001", "CPRB", "11/2024", "98700,00", -65, ""),
                   ("41234.56789.120125.1.3.04-9002", "IRPJ", "12/2024", "22150,00", -40, "Transmitida")]},
    {"base": 10000010, "razao_social": "Kappa Química Industrial Ltda", "fantasia": "Kappa Química",
     "responsavel": "Carla Dias", "tributos": "PIS/COFINS/IPI", "validade": 150,
     "perfil": "NUNCA_CONSULTADO",
     "perdcomps": [("41234.56789.130125.1.3.04-1101", "COFINS", "01/2025", "134900,00", -30, "")]},
]


def linhas_planilha(*, incluir_erros: bool = True) -> list[dict[str, Any]]:
    """Gera as linhas da planilha de teste (uma linha por PER/DCOMP)."""
    linhas: list[dict[str, Any]] = []
    for i, empresa in enumerate(EMPRESAS, start=1):
        cnpj = gerar_cnpj_valido(empresa["base"])
        empresa["cnpj"] = cnpj
        numero_proc = f"PROC-2025-{i:04d}"
        for numero, tributo, periodo, valor, dias_op, situacao in empresa["perdcomps"]:
            linhas.append({
                "cnpj": formatar_cnpj(cnpj),
                "razao_social": empresa["razao_social"],
                "nome_fantasia": empresa["fantasia"],
                "email": f"fiscal@{empresa['fantasia'].lower().replace(' ', '').replace('é','e')}.com.br",
                "responsavel": empresa["responsavel"],
                "numero_procuracao": numero_proc,
                "validade_procuracao": _d(empresa["validade"]),
                "tributos_trabalhados": tributo or empresa["tributos"],
                "numero_perdcomp": numero,
                "valor_compensacao": valor,
                "data_operacao": _d(dias_op),
                "periodo_apuracao": periodo,
                "situacao_compensacao": situacao,
            })
    if incluir_erros:
        # Linhas propositalmente problemáticas, para exercitar validação/correção.
        linhas.append({
            "cnpj": "11.111.111/1111-11", "razao_social": "Empresa CNPJ Inválido Ltda",
            "nome_fantasia": "Teste Erro", "email": "sem-arroba.com.br",
            "responsavel": "Ana Souza", "numero_procuracao": "PROC-2025-9999",
            "validade_procuracao": _d(-400), "tributos_trabalhados": "PIS",
            "numero_perdcomp": "41234.56789.999999.1.3.04-0000",
            "valor_compensacao": "1000,00", "data_operacao": _d(-10),
            "periodo_apuracao": "01/2024", "situacao_compensacao": "Situação Estranha",
        })
        duplicada = dict(linhas[0])
        linhas.append(duplicada)  # PER/DCOMP repetida -> detecção de duplicidade
    return linhas


def mapa_cnpj_perfil() -> dict[str, str]:
    saida = {}
    for empresa in EMPRESAS:
        cnpj = empresa.get("cnpj") or gerar_cnpj_valido(empresa["base"])
        saida[cnpj] = empresa["perfil"]
    return saida
