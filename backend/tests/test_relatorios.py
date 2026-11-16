"""Exportação de relatórios: conteúdo, procedência e controle de acesso."""
from __future__ import annotations

import io

import openpyxl

from app.services.cnpj import gerar_cnpj_valido


def _preparar(api, headers) -> dict:
    cliente = api.post("/api/clientes", headers=headers, json={
        "cnpj": gerar_cnpj_valido(90807060), "razao_social": "Relatório Ltda",
        "responsavel": "Ana"}).json()
    api.post("/api/compensacoes", headers=headers, json={
        "cliente_id": cliente["id"], "numero_perdcomp": "REL-1", "valor_credito": "1000",
        "tributo": "PIS"})
    api.post("/api/procuracoes", headers=headers, json={
        "cliente_id": cliente["id"], "numero": "REL-P1", "data_fim": "2027-01-31"})
    api.post("/api/monitoramento/executar", headers=headers,
             json={"tipo": "COMPLETO", "clientes_ids": [cliente["id"]]})
    return cliente


def test_carteira_excel_tem_abas_e_procedencia(api, headers):
    _preparar(api, headers)
    resp = api.get("/api/relatorios/carteira.xlsx", headers=headers)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert "carteira-" in resp.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Clientes", "Procurações", "PER-DCOMP",
                             "Situação fiscal", "Procedência"]
    clientes = wb["Clientes"]
    assert clientes.max_row >= 2
    cabecalho = [c.value for c in clientes[1]]
    assert "CNPJ" in cabecalho and "Total de débitos" in cabecalho

    procedencia = "\n".join(
        str(c.value) for linha in wb["Procedência"].iter_rows() for c in linha if c.value
    )
    assert "Transmissão x homologação" in procedencia
    assert "não equivale" in procedencia
    assert "SIMULADOR" in procedencia.upper()   # avisa que a fonte é fictícia


def test_pdf_do_cliente(api, headers):
    cliente = _preparar(api, headers)
    resp = api.get(f"/api/relatorios/cliente/{cliente['id']}.pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 2000


def test_pdf_de_outra_organizacao_nega(api, headers, db):
    from app.models.cliente import Cliente
    from app.models.tenant import Organizacao

    outra = Organizacao(nome="Outra Org Relatório")
    db.add(outra)
    db.flush()
    alheio = Cliente(organizacao_id=outra.id, cnpj=gerar_cnpj_valido(80706050),
                     razao_social="Cliente Alheio")
    db.add(alheio)
    db.commit()
    assert api.get(f"/api/relatorios/cliente/{alheio.id}.pdf", headers=headers).status_code == 404


def test_alertas_e_extrato(api, headers):
    _preparar(api, headers)
    alertas = api.get("/api/relatorios/alertas.xlsx", headers=headers, params={"dias": 30})
    assert alertas.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(alertas.content))
    cabecalho = [c.value for c in wb["Alertas"][1]]
    assert "Por que foi gerado" in cabecalho and "Consulta da evidência" in cabecalho

    extrato = api.get("/api/relatorios/consultas.xlsx", headers=headers, params={"dias": 30})
    assert extrato.status_code == 200
    wb2 = openpyxl.load_workbook(io.BytesIO(extrato.content))
    aba = wb2["Extrato de consultas"]
    assert aba.max_row >= 2
    assert [c.value for c in aba[1]][:4] == ["Quando", "Tipo", "CNPJ", "Cliente"]


def test_geracao_de_relatorio_fica_na_auditoria(api, headers):
    _preparar(api, headers)
    api.get("/api/relatorios/carteira.xlsx", headers=headers)
    auditoria = api.get("/api/auditoria", headers=headers,
                        params={"acao": "RELATORIO_GERADO"}).json()
    assert auditoria["total"] >= 1
    assert "xlsx" in auditoria["itens"][0]["descricao"]


def test_auditor_pode_exportar(api):
    token = api.post("/api/auth/login", json={"email": "auditor@exemplo.com.br",
                                              "senha": "Auditor@123456"}).json()["access_token"]
    resp = api.get("/api/relatorios/carteira.xlsx",
                   headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
