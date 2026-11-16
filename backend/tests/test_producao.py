"""Hardening e preparação para produção."""
from __future__ import annotations

from datetime import timedelta

from app.core.config import settings
from app.core.db import utcnow


def test_bloqueio_apos_tentativas_falhas(api, db):
    from app.models.tenant import Usuario
    from sqlalchemy import select

    credenciais = {"email": "analista@exemplo.com.br", "senha": "senha-errada"}
    for _ in range(settings.login_max_tentativas):
        assert api.post("/api/auth/login", json=credenciais).status_code == 401

    bloqueado = api.post("/api/auth/login", json=credenciais)
    assert bloqueado.status_code == 429
    assert "bloqueado" in bloqueado.json()["detail"].lower()
    assert int(bloqueado.headers["retry-after"]) > 0

    # mesmo com a senha correta o acesso permanece bloqueado
    correto = api.post("/api/auth/login",
                       json={"email": "analista@exemplo.com.br", "senha": "Analista@123456"})
    assert correto.status_code == 429

    db.expire_all()
    usuario = db.scalar(select(Usuario).where(Usuario.email == "analista@exemplo.com.br"))
    assert usuario.bloqueado_ate is not None

    # passado o prazo, o acesso volta a funcionar e os contadores zeram
    usuario.bloqueado_ate = utcnow() - timedelta(minutes=1)
    db.commit()
    liberado = api.post("/api/auth/login",
                        json={"email": "analista@exemplo.com.br", "senha": "Analista@123456"})
    assert liberado.status_code == 200
    db.expire_all()
    usuario = db.scalar(select(Usuario).where(Usuario.email == "analista@exemplo.com.br"))
    assert usuario.bloqueado_ate is None and usuario.tentativas_falhas == 0


def test_bloqueio_registrado_na_auditoria(api, headers):
    for _ in range(settings.login_max_tentativas + 1):
        api.post("/api/auth/login", json={"email": "auditor@exemplo.com.br", "senha": "x"})
    auditoria = api.get("/api/auditoria", headers=headers, params={"acao": "LOGIN_BLOQUEADO"}).json()
    assert auditoria["total"] >= 1


def test_prontidao_aponta_pendencias_do_ambiente(api, headers):
    resp = api.get("/api/sistema/prontidao", headers=headers)
    assert resp.status_code == 200
    dados = resp.json()
    itens = {i["item"]: i for i in dados["itens"]}
    assert "Fontes de dados" in itens and "Chave de assinatura (JWT)" in itens
    # no ambiente de teste as fontes estão em simulador: deve acusar como crítico
    assert itens["Fontes de dados"]["situacao"] == "CRITICO"
    assert "simulador" in itens["Fontes de dados"]["recomendacao"]
    assert dados["pronto_para_producao"] is False
    assert dados["resumo"]["total"] == len(dados["itens"])
    assert "infraestrutura" in dados["observacao"]


def test_prontidao_restrita_a_admin(api):
    token = api.post("/api/auth/login", json={"email": "analista@exemplo.com.br",
                                              "senha": "Analista@123456"}).json()["access_token"]
    resp = api.get("/api/sistema/prontidao", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_amostras_vazias_por_padrao(api, headers):
    resp = api.get("/api/sistema/amostras-integracao", headers=headers)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["modo_homologacao_ativo"] is False
    assert dados["total"] == 0
    assert "dados fiscais" in dados["aviso"]


def test_modo_homologacao_captura_amostra(db, monkeypatch):
    """Com o modo ligado, uma falha de chamada vira amostra para diagnóstico."""
    from sqlalchemy import select

    from app.connectors.integra_contador import IntegraSituacaoFiscal
    from app.models.integracao import AmostraIntegracao

    monkeypatch.setattr(settings, "integra_contador_modo_homologacao", True)
    monkeypatch.setattr(settings, "integra_contador_enabled", True)
    monkeypatch.setattr(settings, "integra_contador_base_url", "https://exemplo.invalido")
    monkeypatch.setattr(settings, "integra_contador_token_url", "https://exemplo.invalido/token")
    monkeypatch.setattr(settings, "integra_contador_consumer_key", "k")
    monkeypatch.setattr(settings, "integra_contador_consumer_secret", "s")
    monkeypatch.setattr(settings, "integra_contador_cert_path", "/tmp/inexistente.p12")
    monkeypatch.setenv("MT_IC_SITFIS_ID_SISTEMA", "SITFIS")
    monkeypatch.setenv("MT_IC_SITFIS_ID_SERVICO", "RELATORIO")

    conector = IntegraSituacaoFiscal(db)
    resultado = conector.consultar(cnpj="11222333000181")
    # sem rede/certificado válido, a resposta correta é indisponível — nunca "regular"
    assert resultado.disponibilidade == "INDISPONIVEL"

    amostras = db.scalars(select(AmostraIntegracao)).all()
    assert len(amostras) == 1
    assert amostras[0].dominio.startswith("situação fiscal")
    assert amostras[0].erro
    assert amostras[0].disponibilidade == "INDISPONIVEL"


def test_scripts_de_backup_existem_e_sao_executaveis():
    import os
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for nome in ("backup.sh", "restaurar.sh"):
        caminho = scripts / nome
        assert caminho.is_file(), f"{nome} ausente"
        assert os.access(caminho, os.X_OK), f"{nome} não é executável"
        conteudo = caminho.read_text()
        assert "set -euo pipefail" in conteudo
        assert "sha256sum" in conteudo
    # a restauração precisa recusar sobrescrever o banco em uso sem confirmação
    assert "PERMITIR_SOBRESCREVER" in (scripts / "restaurar.sh").read_text()
