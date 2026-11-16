"""Enumerações de domínio.

Regra de ouro do projeto: transmissão != homologação, e ausência de informação
nunca equivale a ausência de pendência. Por isso existem estados explícitos
para "sem informação" e "indisponível".
"""
from __future__ import annotations

from enum import StrEnum


class Perfil(StrEnum):
    ADMIN = "ADMIN"
    ANALISTA = "ANALISTA"
    AUDITOR = "AUDITOR"


class OrigemInformacao(StrEnum):
    PLANILHA = "PLANILHA"                      # declarado pelo cliente/planilha
    MANUAL = "MANUAL"                          # digitado/anexado por usuário
    IMPORTACAO_RELATORIO = "IMPORTACAO_RELATORIO"  # relatório oficial importado
    SIMULADOR = "SIMULADOR"                    # ambiente de testes (fictício)
    API_INTEGRA_CONTADOR = "API_INTEGRA_CONTADOR"
    AUTOMACAO_NAVEGADOR = "AUTOMACAO_NAVEGADOR"
    SISTEMA = "SISTEMA"                        # derivado por regra interna


FONTES_AUTORIZADAS = {
    OrigemInformacao.API_INTEGRA_CONTADOR,
    OrigemInformacao.IMPORTACAO_RELATORIO,
    OrigemInformacao.AUTOMACAO_NAVEGADOR,
    OrigemInformacao.SIMULADOR,  # só vale como "autorizada" em ambiente de teste
}


class Disponibilidade(StrEnum):
    """Resultado técnico da consulta - separado do resultado de negócio."""
    OK = "OK"                          # consulta concluída com dados
    SEM_DADOS = "SEM_DADOS"            # consulta ok, fonte não retornou registros
    INDISPONIVEL = "INDISPONIVEL"      # fonte fora do ar / erro / bloqueio
    NAO_AUTORIZADO = "NAO_AUTORIZADO"  # falta procuração/poderes/credencial
    NAO_CONSULTADO = "NAO_CONSULTADO"  # nunca consultado automaticamente


class SituacaoProcuracao(StrEnum):
    ATIVA = "ATIVA"
    PROXIMA_VENCIMENTO = "PROXIMA_VENCIMENTO"
    EXPIRADA = "EXPIRADA"
    REVOGADA = "REVOGADA"
    DESCONHECIDA = "DESCONHECIDA"


class Semaforo(StrEnum):
    VERDE = "VERDE"
    AMARELO = "AMARELO"
    VERMELHO = "VERMELHO"
    CINZA = "CINZA"


class SituacaoCompensacao(StrEnum):
    TRANSMITIDA = "TRANSMITIDA"
    EM_PROCESSAMENTO = "EM_PROCESSAMENTO"
    EM_ANALISE = "EM_ANALISE"
    HOMOLOGADA = "HOMOLOGADA"
    NAO_HOMOLOGADA = "NAO_HOMOLOGADA"
    HOMOLOGADA_PARCIALMENTE = "HOMOLOGADA_PARCIALMENTE"
    CANCELADA = "CANCELADA"
    COM_EXIGENCIA = "COM_EXIGENCIA"          # exigência ou intimação
    SEM_INFORMACAO = "SEM_INFORMACAO"        # sem informação atualizada


SITUACOES_FAVORAVEIS = {SituacaoCompensacao.HOMOLOGADA}
SITUACOES_CRITICAS = {
    SituacaoCompensacao.NAO_HOMOLOGADA,
    SituacaoCompensacao.COM_EXIGENCIA,
    SituacaoCompensacao.HOMOLOGADA_PARCIALMENTE,
}


class SituacaoFiscalGeral(StrEnum):
    REGULAR = "REGULAR"                # nenhuma pendência identificada na consulta
    COM_PENDENCIAS = "COM_PENDENCIAS"
    NAO_CONSULTADO = "NAO_CONSULTADO"
    INDISPONIVEL = "INDISPONIVEL"


class CategoriaPendencia(StrEnum):
    DEBITO_PREVIDENCIARIO = "DEBITO_PREVIDENCIARIO"
    DEBITO_FEDERAL = "DEBITO_FEDERAL"
    PENDENCIA_PAGAMENTO = "PENDENCIA_PAGAMENTO"
    DEBITO_EM_COBRANCA = "DEBITO_EM_COBRANCA"
    DEBITO_SUSPENSO = "DEBITO_SUSPENSO"
    PARCELAMENTO = "PARCELAMENTO"
    OBRIGACAO_ACESSORIA = "OBRIGACAO_ACESSORIA"
    OUTROS = "OUTROS"


class TipoAlerta(StrEnum):
    PROCURACAO_VENCENDO = "PROCURACAO_VENCENDO"
    PROCURACAO_EXPIRADA = "PROCURACAO_EXPIRADA"
    PROCURACAO_REVOGADA = "PROCURACAO_REVOGADA"
    PROCURACAO_SEM_VALIDACAO = "PROCURACAO_SEM_VALIDACAO"
    COMPENSACAO_MUDANCA_SITUACAO = "COMPENSACAO_MUDANCA_SITUACAO"
    COMPENSACAO_NAO_HOMOLOGADA = "COMPENSACAO_NAO_HOMOLOGADA"
    COMPENSACAO_PERDEU_HOMOLOGACAO = "COMPENSACAO_PERDEU_HOMOLOGACAO"
    COMPENSACAO_COM_EXIGENCIA = "COMPENSACAO_COM_EXIGENCIA"
    SITUACAO_FISCAL_NOVO_DEBITO = "SITUACAO_FISCAL_NOVO_DEBITO"
    SITUACAO_FISCAL_DEBITO_REMANESCENTE = "SITUACAO_FISCAL_DEBITO_REMANESCENTE"
    SITUACAO_FISCAL_PIOROU = "SITUACAO_FISCAL_PIOROU"
    SITUACAO_FISCAL_MELHOROU = "SITUACAO_FISCAL_MELHOROU"
    CONSULTA_DESATUALIZADA = "CONSULTA_DESATUALIZADA"
    FONTE_INDISPONIVEL = "FONTE_INDISPONIVEL"


class Criticidade(StrEnum):
    INFO = "INFO"
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


ORDEM_CRITICIDADE = {
    Criticidade.INFO: 0,
    Criticidade.BAIXA: 1,
    Criticidade.MEDIA: 2,
    Criticidade.ALTA: 3,
    Criticidade.CRITICA: 4,
}


class StatusAlerta(StrEnum):
    NOVO = "NOVO"
    EM_ANALISE = "EM_ANALISE"
    RESOLVIDO = "RESOLVIDO"
    IGNORADO = "IGNORADO"


class CanalNotificacao(StrEnum):
    SISTEMA = "SISTEMA"
    EMAIL = "EMAIL"


class StatusNotificacao(StrEnum):
    PENDENTE = "PENDENTE"
    ENVIADA = "ENVIADA"
    ERRO = "ERRO"
    DESABILITADO = "DESABILITADO"


class StatusImportacao(StrEnum):
    RASCUNHO = "RASCUNHO"
    VALIDADO = "VALIDADO"
    CONFIRMADO = "CONFIRMADO"
    CANCELADO = "CANCELADO"


class AcaoLinha(StrEnum):
    CRIAR = "CRIAR"
    ATUALIZAR = "ATUALIZAR"
    IGNORAR = "IGNORAR"
    ERRO = "ERRO"
    DUPLICADO = "DUPLICADO"


class TipoMonitoramento(StrEnum):
    PROCURACOES = "PROCURACOES"
    COMPENSACOES = "COMPENSACOES"
    SITUACAO_FISCAL = "SITUACAO_FISCAL"
    COMPLETO = "COMPLETO"


class StatusExecucao(StrEnum):
    EXECUTANDO = "EXECUTANDO"
    CONCLUIDA = "CONCLUIDA"
    CONCLUIDA_COM_FALHAS = "CONCLUIDA_COM_FALHAS"
    FALHOU = "FALHOU"
