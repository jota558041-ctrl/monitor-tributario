"""Configuração central da aplicação (12-factor: tudo por variável de ambiente)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_prefix="MT_", extra="ignore"
    )

    # --- Aplicação ---
    app_name: str = "Monitor Tributário"
    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    debug: bool = True
    api_prefix: str = "/api"

    # --- Banco de dados ---
    # Em produção: postgresql+psycopg://user:pass@host:5432/monitor
    database_url: str = "sqlite+pysqlite:///./monitor_tributario.db"
    sql_echo: bool = False

    # --- Segurança ---
    # OBRIGATÓRIO sobrescrever em produção (MT_SECRET_KEY).
    secret_key: str = "dev-only-insecure-change-me-please-set-MT_SECRET_KEY"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    # Chave Fernet (urlsafe base64 de 32 bytes) para criptografia em repouso de
    # campos sensíveis. Se vazia, derivada da secret_key (apenas dev).
    fernet_key: str = ""
    password_min_length: int = 10
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    # --- Conectores de dados (fontes de informação fiscal) ---
    # manual     -> nenhuma consulta automática; só importação manual de resultado
    # simulador  -> ambiente de testes com dados fictícios (protótipo)
    # integra_contador -> adaptador oficial SERPRO/Integra Contador (requer contrato+certificado)
    connector_procuracao: Literal["manual", "simulador", "integra_contador"] = "simulador"
    connector_compensacao: Literal["manual", "simulador", "integra_contador"] = "simulador"
    connector_situacao_fiscal: Literal["manual", "simulador", "integra_contador"] = "simulador"

    # --- Integra Contador (SERPRO) - desativado por padrão ---
    integra_contador_enabled: bool = False
    integra_contador_base_url: str = ""          # fornecido pelo contrato/doc oficial
    integra_contador_token_url: str = ""
    integra_contador_consumer_key: str = ""
    integra_contador_consumer_secret: str = ""
    integra_contador_cert_path: str = ""         # e-CNPJ A1 (.p12/.pfx) do CONTRATANTE
    integra_contador_cert_password: str = ""
    integra_contador_contratante_cnpj: str = ""
    integra_contador_autor_pedido_cnpj: str = ""
    integra_contador_rate_limit_rpm: int = 30

    # --- Monitoramento agendado ---
    scheduler_enabled: bool = True
    scheduler_timezone: str = "America/Sao_Paulo"
    monitoramento_cron: str = "0 6 * * *"   # diário 06:00
    consulta_desatualizada_dias: int = 7

    # --- Alertas de procuração (dias antes do vencimento) ---
    alerta_procuracao_dias: list[int] = Field(default_factory=lambda: [30, 15, 7, 0])

    # --- E-mail (preparado, desligado por padrão) ---
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "monitor@exemplo.com.br"
    smtp_tls: bool = True

    # --- Camada de IA ---
    ia_enabled: bool = True              # motor de regras determinístico
    ia_llm_enabled: bool = False         # redação opcional via LLM (nunca cria fatos)
    ia_llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str = ""

    # --- Armazenamento de anexos ---
    arquivos_dir: str = ""          # vazio => <raiz do projeto>/arquivos
    upload_max_mb: int = 25

    # --- Retenção / LGPD ---
    retencao_consultas_dias: int = 1825   # 5 anos
    retencao_auditoria_dias: int = 1825

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
