"""Configuração dos testes: banco isolado em arquivo temporário."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="monitor-test-"))
os.environ.setdefault("MT_DATABASE_URL", f"sqlite+pysqlite:///{_tmp}/test.db")
os.environ.setdefault("MT_SCHEDULER_ENABLED", "false")
os.environ.setdefault("MT_SECRET_KEY", "chave-de-teste-com-mais-de-32-bytes-ok!")
os.environ.setdefault("MT_ENVIRONMENT", "test")
os.environ.setdefault("MT_CONNECTOR_PROCURACAO", "simulador")
os.environ.setdefault("MT_CONNECTOR_COMPENSACAO", "simulador")
os.environ.setdefault("MT_CONNECTOR_SITUACAO_FISCAL", "simulador")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.main import app  # noqa: E402
from app.models.cliente import Cliente  # noqa: E402
from app.models.enums import Perfil  # noqa: E402
from app.models.tenant import Organizacao, Usuario  # noqa: E402


@pytest.fixture(scope="function")
def db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    sessao = SessionLocal()
    try:
        yield sessao
    finally:
        sessao.rollback()
        sessao.close()


@pytest.fixture
def organizacao(db):
    org = Organizacao(nome="Org Teste", cnpj="19131243000197")
    db.add(org)
    db.flush()
    db.add_all([
        Usuario(organizacao_id=org.id, nome="Admin", email="admin@exemplo.com.br",
                senha_hash=hash_senha("Admin@123456"), perfil=str(Perfil.ADMIN)),
        Usuario(organizacao_id=org.id, nome="Analista", email="analista@exemplo.com.br",
                senha_hash=hash_senha("Analista@123456"), perfil=str(Perfil.ANALISTA)),
        Usuario(organizacao_id=org.id, nome="Auditor", email="auditor@exemplo.com.br",
                senha_hash=hash_senha("Auditor@123456"), perfil=str(Perfil.AUDITOR)),
    ])
    db.commit()
    return org


@pytest.fixture
def cliente(db, organizacao):
    from app.services.cnpj import gerar_cnpj_valido

    cli = Cliente(organizacao_id=organizacao.id, cnpj=gerar_cnpj_valido(33445566),
                  razao_social="Cliente Teste Ltda", responsavel="Ana")
    db.add(cli)
    db.commit()
    return cli


@pytest.fixture
def api(organizacao):
    with TestClient(app) as cliente_http:
        yield cliente_http


@pytest.fixture
def token_admin(api):
    resp = api.post("/api/auth/login",
                    json={"email": "admin@exemplo.com.br", "senha": "Admin@123456"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def headers(token_admin):
    return {"Authorization": f"Bearer {token_admin}"}
