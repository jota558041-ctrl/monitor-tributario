"""Anexos: validação, controle de acesso, integridade e auditoria."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.services.cnpj import gerar_cnpj_valido

PDF = b"%PDF-1.7\n" + b"conteudo ficticio de despacho decisorio\n" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _cliente(api, headers, base: int) -> dict:
    return api.post("/api/clientes", headers=headers, json={
        "cnpj": gerar_cnpj_valido(base), "razao_social": "Documentos Ltda"}).json()


def _enviar(api, headers, cliente_id: str, *, nome="despacho.pdf", conteudo=PDF,
            categoria="DESPACHO_DECISORIO", restrito=False, **extra):
    return api.post("/api/documentos", headers=headers,
                    files={"arquivo": (nome, conteudo, "application/octet-stream")},
                    data={"cliente_id": cliente_id, "categoria": categoria,
                          "restrito": str(restrito).lower(), **extra})


def test_upload_grava_metadados_e_arquivo(api, headers):
    cliente = _cliente(api, headers, 11223344)
    resp = _enviar(api, headers, cliente["id"], descricao="Despacho do PER/DCOMP 1")
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["nome_original"] == "despacho.pdf"
    assert doc["tipo_mime"] == "application/pdf"
    assert doc["tamanho_bytes"] == len(PDF)
    assert len(doc["sha256"]) == 64
    assert doc["categoria"] == "DESPACHO_DECISORIO"

    lista = api.get("/api/documentos", headers=headers,
                    params={"cliente_id": cliente["id"]}).json()
    assert len(lista) == 1 and lista[0]["id"] == doc["id"]
    assert lista[0]["pode_baixar"] is True


def test_download_devolve_conteudo_e_registra_auditoria(api, headers):
    cliente = _cliente(api, headers, 22334455)
    doc = _enviar(api, headers, cliente["id"]).json()
    resp = api.get(f"/api/documentos/{doc['id']}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.content == PDF
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "despacho.pdf" in resp.headers["content-disposition"]

    auditoria = api.get("/api/auditoria", headers=headers,
                        params={"acao": "DOCUMENTO_VISUALIZADO"}).json()
    assert auditoria["total"] >= 1
    assert auditoria["itens"][0]["entidade_id"] == doc["id"]


@pytest.mark.parametrize("nome,conteudo,trecho", [
    ("malicioso.exe", b"MZ\x90\x00", "não permitida"),
    ("falso.pdf", b"isto nao e um pdf", "não corresponde"),
    ("vazio.pdf", b"", "vazio"),
])
def test_arquivos_recusados(api, headers, nome, conteudo, trecho):
    cliente = _cliente(api, headers, 33445566)
    resp = _enviar(api, headers, cliente["id"], nome=nome, conteudo=conteudo)
    assert resp.status_code == 422
    assert trecho in resp.json()["detail"]


def test_tamanho_maximo(api, headers, monkeypatch):
    cliente = _cliente(api, headers, 44556677)
    monkeypatch.setattr(settings, "upload_max_mb", 1)
    grande = b"%PDF-1.7\n" + b"x" * (2 * 1024 * 1024)
    resp = _enviar(api, headers, cliente["id"], nome="grande.pdf", conteudo=grande)
    assert resp.status_code == 422
    assert "excede o limite" in resp.json()["detail"]


def test_documento_restrito_exige_admin(api, headers):
    cliente = _cliente(api, headers, 55667788)
    doc = _enviar(api, headers, cliente["id"], restrito=True).json()
    assert doc["restrito"] is True

    token = api.post("/api/auth/login", json={"email": "analista@exemplo.com.br",
                                              "senha": "Analista@123456"}).json()["access_token"]
    analista = {"Authorization": f"Bearer {token}"}
    lista = api.get("/api/documentos", headers=analista,
                    params={"cliente_id": cliente["id"]}).json()
    assert lista[0]["pode_baixar"] is False          # aparece, mas bloqueado

    negado = api.get(f"/api/documentos/{doc['id']}/download", headers=analista)
    assert negado.status_code == 403
    assert api.get(f"/api/documentos/{doc['id']}/download", headers=headers).status_code == 200

    auditoria = api.get("/api/auditoria", headers=headers,
                        params={"acao": "DOCUMENTO_ACESSO_NEGADO"}).json()
    assert auditoria["total"] >= 1


def test_duplicidade_avisa(api, headers):
    cliente = _cliente(api, headers, 66778899)
    _enviar(api, headers, cliente["id"])
    segundo = _enviar(api, headers, cliente["id"], nome="copia.pdf").json()
    assert "aviso" in segundo
    assert "idêntico" in segundo["aviso"]


def test_exclusao_apaga_arquivo_e_exige_admin(api, headers):
    cliente = _cliente(api, headers, 77889900)
    doc = _enviar(api, headers, cliente["id"], nome="recibo.png", conteudo=PNG,
                  categoria="COMPROVANTE_PERDCOMP").json()

    token = api.post("/api/auth/login", json={"email": "analista@exemplo.com.br",
                                              "senha": "Analista@123456"}).json()["access_token"]
    assert api.delete(f"/api/documentos/{doc['id']}",
                      headers={"Authorization": f"Bearer {token}"}).status_code == 403

    caminhos = list((Path(settings.arquivos_dir)).rglob("*.png"))
    assert caminhos, "arquivo não foi gravado em disco"
    assert api.delete(f"/api/documentos/{doc['id']}", headers=headers).status_code == 204
    assert not [c for c in caminhos if c.exists()], "arquivo não foi removido do disco"
    assert api.get(f"/api/documentos/{doc['id']}/download", headers=headers).status_code == 404


def test_integridade_detecta_arquivo_adulterado(api, headers, db):
    from app.models.documento import Documento

    cliente = _cliente(api, headers, 88990011)
    doc = _enviar(api, headers, cliente["id"], nome="adulterado.pdf").json()
    # Localiza exatamente o arquivo deste documento (outros testes também gravam PDFs).
    db.expire_all()
    registro = db.get(Documento, doc["id"])
    caminho = Path(settings.arquivos_dir) / registro.caminho_relativo
    assert caminho.is_file()
    caminho.write_bytes(b"%PDF-1.7 conteudo trocado")
    resp = api.get(f"/api/documentos/{doc['id']}/download", headers=headers)
    assert resp.status_code == 410
    assert "integridade" in resp.json()["detail"].lower()


def test_segregacao_por_organizacao(api, headers, db):
    from app.core.db import utcnow
    from app.models.cliente import Cliente
    from app.models.documento import Documento
    from app.models.tenant import Organizacao

    outra = Organizacao(nome="Org Documentos")
    db.add(outra)
    db.flush()
    alheio = Cliente(organizacao_id=outra.id, cnpj=gerar_cnpj_valido(99001122),
                     razao_social="Cliente Alheio")
    db.add(alheio)
    db.flush()
    documento = Documento(
        organizacao_id=outra.id, cliente_id=alheio.id, entidade="CLIENTE",
        categoria="OUTRO", nome_original="x.pdf", caminho_relativo="x/x.pdf",
        tipo_mime="application/pdf", tamanho_bytes=10, sha256="0" * 64,
        created_at=utcnow(),
    )
    db.add(documento)
    db.commit()
    assert api.get(f"/api/documentos/{documento.id}/download", headers=headers).status_code == 404
    lista = api.get("/api/documentos", headers=headers).json()
    assert all(d["id"] != documento.id for d in lista)


def test_vinculo_com_perdcomp(api, headers):
    cliente = _cliente(api, headers, 10111213)
    comp = api.post("/api/compensacoes", headers=headers, json={
        "cliente_id": cliente["id"], "numero_perdcomp": "DOC-1"}).json()
    doc = _enviar(api, headers, cliente["id"], categoria="INTIMACAO",
                  entidade="COMPENSACAO", entidade_id=comp["id"]).json()
    assert doc["entidade"] == "COMPENSACAO" and doc["entidade_id"] == comp["id"]
    vinculados = api.get("/api/documentos", headers=headers,
                         params={"entidade": "COMPENSACAO", "entidade_id": comp["id"]}).json()
    assert len(vinculados) == 1
