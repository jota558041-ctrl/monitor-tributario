"""Schemas de clientes, procurações, compensações, situação fiscal e alertas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import (
    CanalNotificacao,
    Criticidade,
    Disponibilidade,
    Semaforo,
    SituacaoCompensacao,
    SituacaoFiscalGeral,
    SituacaoProcuracao,
    StatusAlerta,
    TipoMonitoramento,
)
from app.schemas.comum import Base


# ------------------------------------------------------------------ cliente --
class ClienteIn(BaseModel):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    email: EmailStr | None = None
    responsavel: str | None = None
    tributos_trabalhados: str | None = None
    telefone: str | None = None
    observacoes: str | None = None
    ativo: bool = True


class ClienteUpdate(BaseModel):
    razao_social: str | None = None
    nome_fantasia: str | None = None
    email: EmailStr | None = None
    responsavel: str | None = None
    tributos_trabalhados: str | None = None
    telefone: str | None = None
    observacoes: str | None = None
    ativo: bool | None = None


class ClienteOut(Base):
    id: str
    cnpj: str
    cnpj_formatado: str | None = None
    razao_social: str
    nome_fantasia: str | None = None
    email: str | None = None
    responsavel: str | None = None
    tributos_trabalhados: str | None = None
    telefone: str | None = None
    observacoes: str | None = None
    ativo: bool
    ultima_consulta_procuracao: datetime | None = None
    ultima_consulta_compensacao: datetime | None = None
    ultima_consulta_fiscal: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HistoricoOut(Base):
    id: str
    campo: str
    valor_anterior: str | None = None
    valor_novo: str | None = None
    origem: str
    usuario_email: str | None = None
    created_at: datetime


# -------------------------------------------------------------- procuração --
class ProcuracaoIn(BaseModel):
    cliente_id: str
    numero: str | None = None
    procurador_doc: str | None = None
    procurador_nome: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    poderes: list[str] | None = None
    servicos_autorizados: list[str] | None = None
    observacoes: str | None = None


class ProcuracaoUpdate(BaseModel):
    """Edição cadastral. Não altera `validada_por_fonte` nem a situação oficial."""
    numero: str | None = None
    procurador_doc: str | None = None
    procurador_nome: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    poderes: list[str] | None = None
    servicos_autorizados: list[str] | None = None
    observacoes: str | None = None


class ProcuracaoOut(Base):
    id: str
    cliente_id: str
    cliente_razao_social: str | None = None
    cliente_cnpj: str | None = None
    numero: str | None = None
    outorgante_cnpj: str
    procurador_doc: str | None = None
    procurador_nome: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    situacao: SituacaoProcuracao
    situacao_declarada: SituacaoProcuracao
    semaforo: Semaforo | None = None
    dias_para_vencer: int | None = None
    poderes: list[str] | None = None
    servicos_autorizados: list[str] | None = None
    origem_informacao: str
    disponibilidade: Disponibilidade
    validada_por_fonte: bool
    consultado_em: datetime | None = None
    observacoes: str | None = None


class ProcuracaoConsultaOut(Base):
    id: str
    origem: str
    disponibilidade: Disponibilidade
    situacao_retornada: str | None = None
    data_fim_retornada: date | None = None
    mensagem: str | None = None
    consultado_em: datetime
    criado_por: str | None = None


# ------------------------------------------------------------- compensação --
class CompensacaoIn(BaseModel):
    cliente_id: str
    numero_perdcomp: str
    tipo_documento: str | None = None
    data_transmissao: date | None = None
    tributo: str | None = None
    periodo_apuracao: str | None = None
    valor_debito: Decimal | None = None
    valor_credito: Decimal | None = None
    situacao_compensacao: SituacaoCompensacao | None = None
    situacao_declaracao: str | None = None
    observacoes: str | None = None


class CompensacaoUpdate(BaseModel):
    """Edição dos dados declarados da PER/DCOMP.

    A situação da compensação NÃO é editável por aqui: ela só muda por consulta
    à fonte ou pelo registro de resultado oficial (que grava proveniência).
    """
    tipo_documento: str | None = None
    data_transmissao: date | None = None
    tributo: str | None = None
    periodo_apuracao: str | None = None
    valor_debito: Decimal | None = None
    valor_credito: Decimal | None = None
    situacao_declaracao: str | None = None
    processo_administrativo: str | None = None
    observacoes: str | None = None


class CompensacaoResultadoManualIn(BaseModel):
    """Importação manual do resultado oficial (sem API disponível)."""
    situacao_compensacao: SituacaoCompensacao
    situacao_declaracao: str | None = None
    consultado_em: datetime | None = None
    tem_despacho_decisorio: bool | None = None
    numero_despacho: str | None = None
    data_despacho: date | None = None
    tem_intimacao: bool | None = None
    prazo_resposta_intimacao: date | None = None
    valor_compensado: Decimal | None = None
    valor_nao_homologado: Decimal | None = None
    resultado_analise: str | None = None
    processo_administrativo: str | None = None
    fonte_descricao: str = Field(
        default="Relatório oficial importado manualmente (e-CAC / PER-DCOMP Web)"
    )
    observacoes: str | None = None


class CompensacaoOut(Base):
    id: str
    cliente_id: str
    cliente_razao_social: str | None = None
    cliente_cnpj: str | None = None
    numero_perdcomp: str
    tipo_documento: str | None = None
    data_transmissao: date | None = None
    tributo: str | None = None
    periodo_apuracao: str | None = None
    valor_debito: Decimal | None = None
    valor_credito: Decimal | None = None
    valor_compensado: Decimal | None = None
    valor_nao_homologado: Decimal | None = None
    situacao_declaracao: str | None = None
    situacao_compensacao: SituacaoCompensacao
    tem_despacho_decisorio: bool | None = None
    numero_despacho: str | None = None
    data_despacho: date | None = None
    tem_intimacao: bool | None = None
    prazo_resposta_intimacao: date | None = None
    resultado_analise: str | None = None
    processo_administrativo: str | None = None
    origem_informacao: str
    disponibilidade: Disponibilidade
    consultado_em: datetime | None = None
    observacoes: str | None = None


class CompensacaoEventoOut(Base):
    id: str
    tipo: str
    situacao_anterior: str | None = None
    situacao_nova: str | None = None
    origem: str
    disponibilidade: str | None = None
    mensagem: str | None = None
    payload: dict[str, Any] | None = None
    ocorrido_em: datetime | None = None
    registrado_em: datetime
    criado_por: str | None = None


# ----------------------------------------------------------- situação fiscal --
class SnapshotOut(Base):
    id: str
    cliente_id: str
    origem: str
    disponibilidade: Disponibilidade
    situacao_geral: SituacaoFiscalGeral
    total_debitos: Decimal
    total_previdenciario: Decimal
    total_federal: Decimal
    total_em_cobranca: Decimal
    total_suspenso: Decimal
    total_parcelado: Decimal
    qtd_pendencias: int
    qtd_obrigacoes_acessorias: int
    pendencias: list[dict[str, Any]]
    mensagem: str | None = None
    consultado_em: datetime
    origem_rotulo: str | None = None
    referencia_evento: str | None = None


class ComparativoOut(Base):
    id: str
    cliente_id: str
    snapshot_anterior_id: str
    snapshot_atual_id: str
    total_anterior: Decimal
    total_atual: Decimal
    diferenca: Decimal
    novos: list[dict[str, Any]]
    baixados: list[dict[str, Any]]
    permanecem: list[dict[str, Any]]
    alterados: list[dict[str, Any]]
    ressalva: str | None = None
    created_at: datetime


class SituacaoFiscalManualIn(BaseModel):
    cliente_id: str
    situacao_geral: SituacaoFiscalGeral = SituacaoFiscalGeral.COM_PENDENCIAS
    consultado_em: datetime | None = None
    pendencias: list[dict[str, Any]] = Field(default_factory=list)
    relatorio_bruto: str | None = None
    referencia_evento: str | None = None


# -------------------------------------------------------------------- alertas --
class AlertaOut(Base):
    id: str
    cliente_id: str | None = None
    cliente_razao_social: str | None = None
    cliente_cnpj: str | None = None
    tipo: str
    criticidade: Criticidade
    titulo: str
    mensagem: str
    explicacao: str | None = None
    evidencias: list[dict[str, Any]]
    entidade: str | None = None
    entidade_id: str | None = None
    status: StatusAlerta
    gerado_em: datetime
    resolvido_em: datetime | None = None
    resolvido_por: str | None = None
    nota_resolucao: str | None = None


class AlertaAcaoIn(BaseModel):
    status: StatusAlerta = StatusAlerta.RESOLVIDO
    nota: str | None = None


class RegraIn(BaseModel):
    nome: str
    tipo_monitoramento: TipoMonitoramento = TipoMonitoramento.COMPLETO
    ativo: bool = True
    cron: str = "0 6 * * *"
    criticidade_minima: Criticidade = Criticidade.BAIXA
    canais: list[CanalNotificacao] = Field(default_factory=lambda: [CanalNotificacao.SISTEMA])
    clientes_escopo: list[str] | None = None
    destinatarios: list[str] | None = None
    parametros: dict[str, Any] | None = None


class RegraOut(Base):
    id: str
    nome: str
    tipo_monitoramento: str
    ativo: bool
    cron: str
    criticidade_minima: str
    canais: list[str]
    clientes_escopo: list[str] | None = None
    destinatarios: list[str] | None = None
    parametros: dict[str, Any] | None = None
    ultima_execucao: datetime | None = None
    proxima_execucao: datetime | None = None
    created_at: datetime


class NotificacaoOut(Base):
    id: str
    alerta_id: str
    canal: str
    destinatario: str | None = None
    status: str
    assunto: str | None = None
    corpo: str | None = None
    erro: str | None = None
    enviada_em: datetime | None = None
    created_at: datetime


# --------------------------------------------------------------- execuções --
class ExecucaoOut(Base):
    id: str
    tipo: str
    status: str
    acionada_por: str
    total_clientes: int
    consultas_ok: int
    consultas_indisponiveis: int
    consultas_nao_autorizadas: int
    alertas_gerados: int
    mudancas_detectadas: int
    erro: str | None = None
    iniciado_em: datetime
    finalizado_em: datetime | None = None


class MonitorarIn(BaseModel):
    tipo: TipoMonitoramento = TipoMonitoramento.COMPLETO
    clientes_ids: list[str] | None = None
    gerar_alertas: bool = True


# -------------------------------------------------------------- simulação --
class SimulacaoIn(BaseModel):
    cliente_id: str
    cenario: str
    parametros: dict[str, Any] | None = None
