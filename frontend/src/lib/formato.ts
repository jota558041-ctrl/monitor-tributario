export function brl(valor: string | number | null | undefined): string {
  const numero = typeof valor === "string" ? Number(valor) : valor ?? 0;
  if (numero === null || Number.isNaN(numero)) return "—";
  return numero.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function numero(valor: number | null | undefined): string {
  return (valor ?? 0).toLocaleString("pt-BR");
}

export function data(valor?: string | null): string {
  if (!valor) return "—";
  const d = new Date(valor.length <= 10 ? `${valor}T12:00:00` : valor);
  if (Number.isNaN(d.getTime())) return valor;
  return d.toLocaleDateString("pt-BR");
}

export function dataHora(valor?: string | null): string {
  if (!valor) return "—";
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function cnpj(valor?: string | null): string {
  if (!valor) return "—";
  const d = valor.replace(/\D/g, "");
  if (d.length !== 14) return valor;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

const NOMES: Record<string, string> = {
  TRANSMITIDA: "Transmitida", EM_PROCESSAMENTO: "Em processamento", EM_ANALISE: "Em análise",
  HOMOLOGADA: "Homologada", NAO_HOMOLOGADA: "Não homologada",
  HOMOLOGADA_PARCIALMENTE: "Homologada parcialmente", CANCELADA: "Cancelada",
  COM_EXIGENCIA: "Com exigência/intimação", SEM_INFORMACAO: "Sem informação atualizada",
  ATIVA: "Ativa", PROXIMA_VENCIMENTO: "Próxima do vencimento", EXPIRADA: "Expirada",
  REVOGADA: "Revogada", DESCONHECIDA: "Desconhecida",
  REGULAR: "Sem pendências", COM_PENDENCIAS: "Com pendências",
  NAO_CONSULTADO: "Não consultado", INDISPONIVEL: "Indisponível", NAO_AUTORIZADO: "Não autorizado",
  OK: "OK", SEM_DADOS: "Sem dados",
  DEBITO_FEDERAL: "Débito federal", DEBITO_PREVIDENCIARIO: "Débito previdenciário",
  DEBITO_EM_COBRANCA: "Débito em cobrança", DEBITO_SUSPENSO: "Débito suspenso",
  PARCELAMENTO: "Parcelamento", OBRIGACAO_ACESSORIA: "Obrigação acessória",
  PENDENCIA_PAGAMENTO: "Pendência de pagamento", OUTROS: "Outros",
  COMPLETO: "Completo", PROCURACOES: "Procurações", COMPENSACOES: "Compensações",
  SITUACAO_FISCAL: "Situação fiscal", CONCLUIDA: "Concluída",
  CONCLUIDA_COM_FALHAS: "Concluída com falhas", EXECUTANDO: "Executando", FALHOU: "Falhou",
  NOVO: "Novo", EM_ANALISE_ALERTA: "Em análise", RESOLVIDO: "Resolvido", IGNORADO: "Ignorado",
  CRIAR: "Criar", ATUALIZAR: "Atualizar", DUPLICADO: "Duplicado", ERRO: "Erro", IGNORAR: "Ignorar",
  VALIDADO: "Validado", CONFIRMADO: "Confirmado", CANCELADO: "Cancelado", RASCUNHO: "Rascunho",
  ENVIADA: "Enviada", PENDENTE: "Pendente", DESABILITADO: "Desabilitado",
  PROCURACAO_VENCENDO: "Procuração vencendo", PROCURACAO_EXPIRADA: "Procuração expirada",
  PROCURACAO_REVOGADA: "Procuração revogada",
  PROCURACAO_SEM_VALIDACAO: "Procuração sem validação",
  COMPENSACAO_MUDANCA_SITUACAO: "Mudança de situação na PER/DCOMP",
  COMPENSACAO_NAO_HOMOLOGADA: "PER/DCOMP não homologada",
  COMPENSACAO_PERDEU_HOMOLOGACAO: "PER/DCOMP deixou de ser homologada",
  COMPENSACAO_COM_EXIGENCIA: "PER/DCOMP com exigência",
  SITUACAO_FISCAL_NOVO_DEBITO: "Novo débito",
  SITUACAO_FISCAL_DEBITO_REMANESCENTE: "Débito remanescente",
  SITUACAO_FISCAL_PIOROU: "Aumento de débitos",
  SITUACAO_FISCAL_MELHOROU: "Redução de débitos",
  CONSULTA_DESATUALIZADA: "Consulta desatualizada", FONTE_INDISPONIVEL: "Fonte indisponível",
  LOGIN_FALHA: "Login (falha)", CONSULTA_FONTE: "Consulta à fonte",
  RESULTADO_MANUAL: "Resultado manual", IMPORTACAO_CARREGADA: "Importação carregada",
  IMPORTACAO_CORRECAO: "Correção de importação",
  IMPORTACAO_CONFIRMADA: "Importação confirmada", ALERTA_ACAO: "Tratamento de alerta",
  IA_RESUMO: "Resumo (IA)", MONITORAMENTO: "Monitoramento", SIMULACAO: "Simulação",
  LEITURA: "Leitura", CRIACAO: "Criação", ALTERACAO: "Alteração", EXCLUSAO: "Exclusão",
  TROCA_SENHA: "Troca de senha", LOGIN: "Login",
  PROCURACAO: "Procurações", COMPENSACAO: "Compensações", CLIENTE: "Clientes",
  SITUACAO_FISCAL_DOMINIO: "Situação fiscal", SISTEMA: "Sistema", SIMULADOR: "Simulador",
  PLANILHA: "Planilha", MANUAL: "Manual", IMPORTACAO_RELATORIO: "Relatório importado",
  API_INTEGRA_CONTADOR: "API Integra Contador", AUTOMACAO_NAVEGADOR: "Automação de navegador",
};

export function rotulo(valor?: string | null): string {
  if (!valor) return "—";
  if (NOMES[valor]) return NOMES[valor];
  return valor.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

export const CORES = {
  marinho: "#0f2244", azul: "#2563eb", azulClaro: "#9dc1f7", cinza: "#c6ced9",
  verde: "#0f8a4d", amarelo: "#b8860b", vermelho: "#c0392b",
};

export const COR_SITUACAO_COMPENSACAO: Record<string, string> = {
  HOMOLOGADA: "verde",
  HOMOLOGADA_PARCIALMENTE: "amarelo",
  NAO_HOMOLOGADA: "vermelho",
  COM_EXIGENCIA: "vermelho",
  EM_ANALISE: "azul",
  EM_PROCESSAMENTO: "azul",
  TRANSMITIDA: "azul",
  CANCELADA: "cinza",
  SEM_INFORMACAO: "cinza",
};

export const COR_CRITICIDADE: Record<string, string> = {
  CRITICA: "vermelho", ALTA: "vermelho", MEDIA: "amarelo", BAIXA: "azul", INFO: "cinza",
};

export const COR_DISPONIBILIDADE: Record<string, string> = {
  OK: "verde", SEM_DADOS: "cinza", INDISPONIVEL: "vermelho",
  NAO_AUTORIZADO: "vermelho", NAO_CONSULTADO: "cinza",
};

export const COR_SITUACAO_FISCAL: Record<string, string> = {
  REGULAR: "verde", COM_PENDENCIAS: "vermelho",
  NAO_CONSULTADO: "cinza", INDISPONIVEL: "amarelo",
};
