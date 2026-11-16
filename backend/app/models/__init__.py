"""Registro de todos os modelos ORM."""
from app.models.alerta import Alerta, Notificacao, RegraMonitoramento
from app.models.cliente import Cliente, ClienteHistorico
from app.models.compensacao import Compensacao, CompensacaoEvento
from app.models.documento import Documento
from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
from app.models.importacao import Importacao, ImportacaoLinha
from app.models.integracao import AmostraIntegracao, CredencialIntegracao
from app.models.monitoramento import EstadoSimulado, ExecucaoMonitoramento
from app.models.procuracao import Procuracao, ProcuracaoConsulta
from app.models.tenant import AuditLog, Organizacao, Usuario

__all__ = [
    "Alerta", "AmostraIntegracao", "AuditLog", "Cliente", "ClienteHistorico",
    "Compensacao",
    "CompensacaoEvento", "CredencialIntegracao", "Documento", "EstadoSimulado",
    "ExecucaoMonitoramento", "Importacao", "ImportacaoLinha", "Notificacao",
    "Organizacao", "Procuracao", "ProcuracaoConsulta", "RegraMonitoramento",
    "SituacaoFiscalComparativo", "SituacaoFiscalSnapshot", "Usuario",
]
