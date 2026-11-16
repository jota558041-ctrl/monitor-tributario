"""Edição e exclusão manual: devem respeitar as regras de proveniência."""
from __future__ import annotations

from datetime import date, timedelta

from app.services.cnpj import gerar_cnpj_valido


def _cliente(api, headers, base: int, nome: str) -> dict:
    resp = api.post("/api/clientes", headers=headers,
                    json={"cnpj": gerar_cnpj_valido(base), "razao_social": nome})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_editar_cliente_registra_historico(api, headers):
    cliente = _cliente(api, headers, 10203040, "Editar Ltda")
    resp = api.patch(f"/api/clientes/{cliente['id']}", headers=headers,
                     json={"responsavel": "Nova Responsável", "email": "novo@exemplo.com.br"})
    assert resp.status_code == 200
    assert resp.json()["responsavel"] == "Nova Responsável"
    historico = api.get(f"/api/clientes/{cliente['id']}/historico", headers=headers).json()
    campos = {h["campo"] for h in historico}
    assert {"responsavel", "email"} <= campos


def test_procuracao_manual_nao_fica_validada(api, headers):
    cliente = _cliente(api, headers, 20304050, "Procuração Manual Ltda")
    resp = api.post("/api/procuracoes", headers=headers, json={
        "cliente_id": cliente["id"], "numero": "PM-1",
        "data_fim": (date.today() + timedelta(days=200)).isoformat(),
    })
    assert resp.status_code == 201, resp.text
    proc = resp.json()
    assert proc["validada_por_fonte"] is False
    assert proc["situacao"] == "DESCONHECIDA"
    assert proc["situacao_declarada"] == "ATIVA"
    assert proc["semaforo"] == "CINZA"


def test_editar_procuracao_nao_valida_por_fonte(api, headers):
    cliente = _cliente(api, headers, 30405060, "Edita Procuração Ltda")
    proc = api.post("/api/procuracoes", headers=headers, json={
        "cliente_id": cliente["id"], "numero": "EP-1",
        "data_fim": (date.today() + timedelta(days=10)).isoformat(),
    }).json()
    nova_validade = (date.today() + timedelta(days=400)).isoformat()
    resp = api.patch(f"/api/procuracoes/{proc['id']}", headers=headers,
                     json={"data_fim": nova_validade, "procurador_doc": "52998224725"})
    assert resp.status_code == 200, resp.text
    atualizada = resp.json()
    assert atualizada["data_fim"] == nova_validade
    assert atualizada["validada_por_fonte"] is False      # edição manual não valida
    assert atualizada["situacao"] == "DESCONHECIDA"
    assert atualizada["situacao_declarada"] == "ATIVA"
    assert atualizada["semaforo"] == "CINZA"


def test_editar_compensacao_nao_muda_situacao_e_gera_evento(api, headers):
    cliente = _cliente(api, headers, 40506070, "Edita PERDCOMP Ltda")
    comp = api.post("/api/compensacoes", headers=headers, json={
        "cliente_id": cliente["id"], "numero_perdcomp": "EC-1", "valor_credito": "1000",
    }).json()
    assert comp["situacao_compensacao"] == "SEM_INFORMACAO"

    resp = api.patch(f"/api/compensacoes/{comp['id']}", headers=headers,
                     json={"tributo": "PIS", "periodo_apuracao": "03/2024",
                           "valor_credito": "2500.00",
                           "situacao_compensacao": "HOMOLOGADA"})  # campo inexistente no schema
    assert resp.status_code == 200, resp.text
    atualizada = resp.json()
    assert atualizada["tributo"] == "PIS"
    assert atualizada["valor_credito"] == "2500.00"
    # o campo ignorado pelo schema não pode ter alterado a situação
    assert atualizada["situacao_compensacao"] == "SEM_INFORMACAO"

    historico = api.get(f"/api/compensacoes/{comp['id']}/historico", headers=headers).json()
    tipos = [h["tipo"] for h in historico]
    assert "EDICAO_MANUAL" in tipos


def test_exclusao_restrita_a_admin(api, headers):
    cliente = _cliente(api, headers, 50607080, "Exclusão Ltda")
    proc = api.post("/api/procuracoes", headers=headers,
                    json={"cliente_id": cliente["id"], "numero": "EX-1"}).json()
    comp = api.post("/api/compensacoes", headers=headers,
                    json={"cliente_id": cliente["id"], "numero_perdcomp": "EX-C1"}).json()

    token = api.post("/api/auth/login", json={"email": "analista@exemplo.com.br",
                                              "senha": "Analista@123456"}).json()["access_token"]
    cabecalho_analista = {"Authorization": f"Bearer {token}"}
    assert api.delete(f"/api/procuracoes/{proc['id']}", headers=cabecalho_analista).status_code == 403
    assert api.delete(f"/api/compensacoes/{comp['id']}", headers=cabecalho_analista).status_code == 403

    assert api.delete(f"/api/procuracoes/{proc['id']}", headers=headers).status_code == 204
    assert api.delete(f"/api/compensacoes/{comp['id']}", headers=headers).status_code == 204
    assert api.get(f"/api/procuracoes/{proc['id']}", headers=headers).status_code == 404

    auditoria = api.get("/api/auditoria", headers=headers, params={"acao": "EXCLUSAO"}).json()
    assert auditoria["total"] >= 2


def test_gestao_de_usuarios(api, headers):
    criado = api.post("/api/usuarios", headers=headers, json={
        "nome": "Novo Analista", "email": "novo.analista@exemplo.com.br",
        "senha": "Senha@Forte123", "perfil": "ANALISTA"}).json()
    assert criado["ativo"] is True

    # senha fraca é recusada
    fraca = api.post("/api/usuarios", headers=headers, json={
        "nome": "Fraco", "email": "fraco@exemplo.com.br", "senha": "12345678", "perfil": "ANALISTA"})
    assert fraca.status_code == 422

    desativado = api.patch(f"/api/usuarios/{criado['id']}", headers=headers,
                           json={"ativo": False}).json()
    assert desativado["ativo"] is False
    login = api.post("/api/auth/login", json={"email": "novo.analista@exemplo.com.br",
                                              "senha": "Senha@Forte123"})
    assert login.status_code == 403        # usuário desativado não entra

    api.patch(f"/api/usuarios/{criado['id']}", headers=headers,
              json={"ativo": True, "perfil": "AUDITOR", "senha": "Outra@Senha456"})
    novo_login = api.post("/api/auth/login", json={"email": "novo.analista@exemplo.com.br",
                                                   "senha": "Outra@Senha456"})
    assert novo_login.status_code == 200
    assert novo_login.json()["usuario"]["perfil"] == "AUDITOR"
