"""Testes de API: autenticação, importação, monitoramento, alertas e permissões."""
from __future__ import annotations

from datetime import date, timedelta

from app.services.cnpj import formatar_cnpj, gerar_cnpj_valido
from app.services.planilha import gerar_planilha

CNPJ_A = gerar_cnpj_valido(44556677)
CNPJ_B = gerar_cnpj_valido(55667788)


def _planilha() -> bytes:
    validade = (date.today() + timedelta(days=10)).strftime("%d/%m/%Y")
    linhas = [
        {"cnpj": formatar_cnpj(CNPJ_A), "razao_social": "Cliente API Um Ltda",
         "nome_fantasia": "API Um", "email": "um@exemplo.com.br", "responsavel": "Ana",
         "numero_procuracao": "PR-1", "validade_procuracao": validade,
         "tributos_trabalhados": "PIS/COFINS", "numero_perdcomp": "PD-API-1",
         "valor_compensacao": "10.000,00",
         "data_operacao": (date.today() - timedelta(days=30)).strftime("%d/%m/%Y"),
         "periodo_apuracao": "01/2024", "situacao_compensacao": "Transmitida"},
        {"cnpj": formatar_cnpj(CNPJ_A), "razao_social": "Cliente API Um Ltda",
         "numero_procuracao": "PR-1", "validade_procuracao": validade,
         "numero_perdcomp": "PD-API-2", "valor_compensacao": "2.500,00",
         "data_operacao": (date.today() - timedelta(days=20)).strftime("%d/%m/%Y"),
         "periodo_apuracao": "02/2024", "situacao_compensacao": ""},
        {"cnpj": "11.111.111/1111-11", "razao_social": "Inválido Ltda",
         "numero_perdcomp": "PD-API-3", "valor_compensacao": "1,00"},
        {"cnpj": formatar_cnpj(CNPJ_A), "razao_social": "Cliente API Um Ltda",
         "numero_perdcomp": "PD-API-1", "valor_compensacao": "10.000,00"},  # duplicada
    ]
    return gerar_planilha(linhas)


def test_health_e_info_sem_autenticacao(api):
    assert api.get("/api/health").json()["status"] == "ok"
    info = api.get("/api/info").json()
    assert info["conectores"]["situacao_fiscal"] == "simulador"


def test_login_invalido(api):
    resp = api.post("/api/auth/login", json={"email": "admin@exemplo.com.br", "senha": "errada"})
    assert resp.status_code == 401


def test_endpoint_protegido_exige_token(api):
    assert api.get("/api/clientes").status_code == 401


def test_auditor_nao_pode_escrever(api):
    token = api.post("/api/auth/login", json={"email": "auditor@exemplo.com.br",
                                              "senha": "Auditor@123456"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/clientes", headers=h).status_code == 200
    resp = api.post("/api/clientes", headers=h,
                    json={"cnpj": CNPJ_B, "razao_social": "Teste"})
    assert resp.status_code == 403


def test_analista_nao_cria_usuario(api):
    token = api.post("/api/auth/login", json={"email": "analista@exemplo.com.br",
                                              "senha": "Analista@123456"}).json()["access_token"]
    resp = api.post("/api/usuarios", headers={"Authorization": f"Bearer {token}"},
                    json={"nome": "X", "email": "x@exemplo.com.br", "senha": "Senha@123456"})
    assert resp.status_code == 403


def test_cliente_com_cnpj_invalido_e_recusado(api, headers):
    resp = api.post("/api/clientes", headers=headers,
                    json={"cnpj": "11111111111111", "razao_social": "Teste"})
    assert resp.status_code == 422


def test_fluxo_completo_importacao_monitoramento_alertas(api, headers):
    # 1) upload da planilha
    resp = api.post("/api/importacoes", headers=headers,
                    files={"arquivo": ("planilha.xlsx", _planilha(),
                                       "application/vnd.openxmlformats-officedocument."
                                       "spreadsheetml.sheet")})
    assert resp.status_code == 201, resp.text
    corpo = resp.json()
    assert corpo["status"] == "VALIDADO"
    assert corpo["mapeamento"]["CNPJ"] == "cnpj"
    linhas = corpo["linhas"]
    assert len(linhas) == 4
    com_erro = [x for x in linhas if x["erros"]]
    duplicadas = [x for x in linhas if x["acao"] == "DUPLICADO"]
    assert len(com_erro) == 1 and "CNPJ inválido" in com_erro[0]["erros"][0]["mensagem"]
    assert len(duplicadas) == 1

    # 2) correção da linha com erro
    importacao_id = corpo["id"]
    resp = api.patch(f"/api/importacoes/{importacao_id}/linhas/{com_erro[0]['id']}",
                     headers=headers,
                     json={"correcoes": {"cnpj": formatar_cnpj(CNPJ_B),
                                         "razao_social": "Cliente API Dois Ltda"}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["linha"]["erros"] == []
    assert resp.json()["linha"]["acao"] == "CRIAR"

    # 3) confirmação
    resp = api.post(f"/api/importacoes/{importacao_id}/confirmar", headers=headers)
    assert resp.status_code == 200, resp.text
    resumo = resp.json()["resumo"]
    assert resumo["clientes_criados"] == 2
    assert resumo["compensacoes_criadas"] == 3      # a duplicada não entra
    assert resumo["linhas_ignoradas"] == 1

    # 4) clientes e procurações: nada é presumido ativo
    clientes = api.get("/api/clientes", headers=headers).json()
    assert clientes["total"] == 2
    painel = api.get("/api/procuracoes/painel", headers=headers).json()
    assert painel["semaforo"]["CINZA"] >= 1
    assert painel["semaforo"]["VERDE"] == 0

    # 5) PER/DCOMP sem situação informada = SEM_INFORMACAO
    comps = api.get("/api/compensacoes", headers=headers).json()["itens"]
    por_numero = {c["numero_perdcomp"]: c for c in comps}
    assert por_numero["PD-API-1"]["situacao_compensacao"] == "TRANSMITIDA"
    assert por_numero["PD-API-2"]["situacao_compensacao"] == "SEM_INFORMACAO"
    assert por_numero["PD-API-1"]["disponibilidade"] == "NAO_CONSULTADO"

    # 6) primeira execução do monitoramento
    resp = api.post("/api/monitoramento/executar", headers=headers,
                    json={"tipo": "COMPLETO"})
    assert resp.status_code == 200, resp.text
    execucao = resp.json()["execucao"]
    assert execucao["total_clientes"] == 2
    assert execucao["consultas_ok"] >= 1

    painel = api.get("/api/procuracoes/painel", headers=headers).json()
    assert painel["semaforo"]["AMARELO"] >= 1       # validada e vencendo em 10 dias

    # 7) simulação de mudança + nova execução gera alerta de mudança
    cliente_id = next(c["id"] for c in clientes["itens"] if c["cnpj"] == CNPJ_A)
    resp = api.post("/api/simulacao/aplicar", headers=headers,
                    json={"cliente_id": cliente_id, "cenario": "NAO_HOMOLOGAR",
                          "parametros": {"numero_perdcomp": "PD-API-1"}})
    assert resp.status_code == 200, resp.text
    api.post("/api/monitoramento/executar", headers=headers, json={"tipo": "COMPENSACOES"})

    alertas = api.get("/api/alertas", headers=headers,
                      params={"tipo": "COMPENSACAO_NAO_HOMOLOGADA"}).json()
    assert alertas["total"] >= 1
    alerta = alertas["itens"][0]
    assert alerta["explicacao"]
    assert alerta["evidencias"][0]["consultado_em"]
    assert alerta["criticidade"] == "CRITICA"

    # 8) notificações registradas
    notificacoes = api.get("/api/notificacoes", headers=headers).json()
    assert notificacoes["total"] >= 1

    # 9) dashboard reflete os números
    painel_geral = api.get("/api/dashboard/resumo", headers=headers).json()
    assert painel_geral["clientes"]["total"] == 2
    assert painel_geral["compensacoes"]["nao_homologadas"] >= 1
    assert painel_geral["fontes"]["procuracao"] == "simulador"

    # 10) resumo da IA com fonte, data e limites
    ia = api.get(f"/api/ia/resumo/{cliente_id}", headers=headers).json()
    assert ia["metodo"] == "REGRAS"
    assert "PER/DCOMP" in ia["resumo"]
    assert len(ia["limites"]) == 3
    atencao = api.get("/api/ia/clientes-atencao", headers=headers).json()
    assert atencao["itens"][0]["qtd_alertas"] >= 1

    # 11) resolver alerta
    resp = api.post(f"/api/alertas/{alerta['id']}/acao", headers=headers,
                    json={"status": "RESOLVIDO", "nota": "Conferido no e-CAC."})
    assert resp.json()["status"] == "RESOLVIDO"

    # 12) auditoria registrou as ações
    auditoria = api.get("/api/auditoria", headers=headers).json()
    acoes = {i["acao"] for i in auditoria["itens"]}
    assert {"LOGIN", "IMPORTACAO_CONFIRMADA", "MONITORAMENTO", "ALERTA_ACAO"} <= acoes


def test_resultado_manual_de_perdcomp(api, headers):
    cliente = api.post("/api/clientes", headers=headers,
                       json={"cnpj": CNPJ_B, "razao_social": "Manual Ltda"}).json()
    comp = api.post("/api/compensacoes", headers=headers,
                    json={"cliente_id": cliente["id"], "numero_perdcomp": "PD-MAN-1",
                          "valor_credito": "1000"}).json()
    assert comp["situacao_compensacao"] == "SEM_INFORMACAO"
    resp = api.post(f"/api/compensacoes/{comp['id']}/resultado-manual", headers=headers,
                    json={"situacao_compensacao": "HOMOLOGADA",
                          "tem_despacho_decisorio": True, "numero_despacho": "DD-9",
                          "valor_compensado": "1000"})
    assert resp.status_code == 200, resp.text
    atualizada = resp.json()["compensacao"]
    assert atualizada["situacao_compensacao"] == "HOMOLOGADA"
    assert atualizada["origem_informacao"] == "IMPORTACAO_RELATORIO"
    historico = api.get(f"/api/compensacoes/{comp['id']}/historico", headers=headers).json()
    assert len(historico) == 2


def test_situacao_fiscal_manual_e_comparativo(api, headers):
    cliente = api.post("/api/clientes", headers=headers,
                       json={"cnpj": gerar_cnpj_valido(66778899),
                             "razao_social": "Fiscal Manual Ltda"}).json()
    base = {"cliente_id": cliente["id"], "situacao_geral": "COM_PENDENCIAS"}
    api.post("/api/situacao-fiscal/manual", headers=headers, json={
        **base, "pendencias": [{"categoria": "DEBITO_FEDERAL", "codigo": "Z1",
                                "descricao": "Débito", "periodo": "01/2024",
                                "valor": "15000.00"}]})
    api.post("/api/situacao-fiscal/manual", headers=headers, json={
        **base, "pendencias": [{"categoria": "DEBITO_FEDERAL", "codigo": "Z1",
                                "descricao": "Débito", "periodo": "01/2024",
                                "valor": "5000.00"}]})
    comparativos = api.get(f"/api/situacao-fiscal/{cliente['id']}/comparativos",
                           headers=headers).json()
    assert comparativos[0]["diferenca"] == "-10000.00"
    assert comparativos[0]["ressalva"]
    visao = api.get("/api/situacao-fiscal/visao-geral", headers=headers).json()
    linha = next(x for x in visao if x["cliente_id"] == cliente["id"])
    assert linha["total_debitos"] == "5000.00"
    assert linha["variacao"] == "-10000.00"


def test_modelo_de_planilha_e_campos(api, headers):
    resp = api.get("/api/importacoes/modelo", headers=headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"      # xlsx é um zip
    campos = api.get("/api/importacoes/campos", headers=headers).json()
    assert any(c["nome"] == "numero_perdcomp" for c in campos)


def test_integracoes_status_expoe_limitacoes(api, headers):
    dados = api.get("/api/integracoes/status", headers=headers).json()
    assert dados["integra_contador"]["habilitado"] is False
    assert any("simulador" in f["conector_configurado"] for f in dados["fontes"])
    assert len(dados["regras_de_ouro"]) == 4


def test_segregacao_por_organizacao(api, headers, db):
    from app.core.security import hash_senha
    from app.models.cliente import Cliente
    from app.models.enums import Perfil
    from app.models.tenant import Organizacao, Usuario

    outra = Organizacao(nome="Outra Org")
    db.add(outra)
    db.flush()
    db.add(Usuario(organizacao_id=outra.id, nome="Outro Admin",
                   email="outro@exemplo.com.br", senha_hash=hash_senha("Outro@123456"),
                   perfil=str(Perfil.ADMIN)))
    alheio = Cliente(organizacao_id=outra.id, cnpj=gerar_cnpj_valido(77889900),
                     razao_social="Cliente de Outra Org")
    db.add(alheio)
    db.commit()

    lista = api.get("/api/clientes", headers=headers).json()
    assert all(c["razao_social"] != "Cliente de Outra Org" for c in lista["itens"])
    assert api.get(f"/api/clientes/{alheio.id}", headers=headers).status_code == 404
