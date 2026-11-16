"""Registro de credenciais de integração (valores sensíveis cifrados)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt, encrypt
from app.core.db import Base, Timestamps, UUIDPk


class TextoCriptografado(TypeDecorator):
    """Campo cifrado em repouso com Fernet (AES-128-CBC + HMAC)."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)


class AmostraIntegracao(UUIDPk, Base):
    """Captura de requisição/resposta brutas das fontes, em modo homologação.

    Serve exclusivamente para mapear os campos reais de um contrato novo. Fica
    desligada por padrão (MT_INTEGRA_CONTADOR_MODO_HOMOLOGACAO=false) porque as
    respostas podem conter dados fiscais completos do contribuinte, e seu
    acesso é restrito ao perfil ADMIN.
    """
    __tablename__ = "amostra_integracao"

    organizacao_id: Mapped[str | None] = mapped_column(String(32), index=True)
    dominio: Mapped[str] = mapped_column(String(40), nullable=False)      # procuracao, ...
    provedor: Mapped[str] = mapped_column(String(60), nullable=False)
    contribuinte: Mapped[str | None] = mapped_column(String(14))
    id_sistema: Mapped[str | None] = mapped_column(String(60))
    id_servico: Mapped[str | None] = mapped_column(String(60))
    http_status: Mapped[int | None] = mapped_column()
    disponibilidade: Mapped[str | None] = mapped_column(String(30))
    requisicao: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resposta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    erro: Mapped[str | None] = mapped_column(Text)
    duracao_ms: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class CredencialIntegracao(UUIDPk, Timestamps, Base):
    """Credenciais de acesso a fontes oficiais.

    NUNCA armazena senha gov.br. A chave privada do certificado digital não é
    persistida: guarda-se o caminho do arquivo .p12/.pfx em volume protegido e
    a senha cifrada. Ver docs/SEGURANCA.md.
    """
    __tablename__ = "credencial_integracao"

    organizacao_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    provedor: Mapped[str] = mapped_column(String(60), nullable=False)  # INTEGRA_CONTADOR, ...
    descricao: Mapped[str | None] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consumer_key: Mapped[str | None] = mapped_column(TextoCriptografado)
    consumer_secret: Mapped[str | None] = mapped_column(TextoCriptografado)
    certificado_path: Mapped[str | None] = mapped_column(String(500))
    certificado_senha: Mapped[str | None] = mapped_column(TextoCriptografado)
    contratante_cnpj: Mapped[str | None] = mapped_column(String(14))
    autor_pedido_dados: Mapped[str | None] = mapped_column(String(14))
    metadados: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
