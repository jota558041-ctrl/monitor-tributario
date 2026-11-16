/** Cliente HTTP da API + tipos principais. */
const CHAVE_TOKEN = "mt_token";
const CHAVE_USUARIO = "mt_usuario";

export type Perfil = "ADMIN" | "ANALISTA" | "AUDITOR";

export interface Usuario {
  id: string; nome: string; email: string; perfil: Perfil;
  ativo: boolean; organizacao_id: string; ultimo_login?: string | null;
}

export interface Pagina<T> { itens: T[]; total: number; pagina: number; tamanho: number }

export interface Cliente {
  id: string; cnpj: string; cnpj_formatado?: string; razao_social: string;
  nome_fantasia?: string | null; email?: string | null; responsavel?: string | null;
  tributos_trabalhados?: string | null; telefone?: string | null; observacoes?: string | null;
  ativo: boolean; ultima_consulta_procuracao?: string | null;
  ultima_consulta_compensacao?: string | null; ultima_consulta_fiscal?: string | null;
  created_at: string; updated_at: string;
}

export type Semaforo = "VERDE" | "AMARELO" | "VERMELHO" | "CINZA";

export interface Procuracao {
  id: string; cliente_id: string; cliente_razao_social?: string; cliente_cnpj?: string;
  numero?: string | null; outorgante_cnpj: string; procurador_doc?: string | null;
  data_inicio?: string | null; data_fim?: string | null; situacao: string;
  situacao_declarada: string; semaforo?: Semaforo; dias_para_vencer?: number | null;
  poderes?: string[] | null; servicos_autorizados?: string[] | null;
  origem_informacao: string; disponibilidade: string; validada_por_fonte: boolean;
  consultado_em?: string | null; observacoes?: string | null;
}

export interface Compensacao {
  id: string; cliente_id: string; cliente_razao_social?: string; cliente_cnpj?: string;
  numero_perdcomp: string; data_transmissao?: string | null; tributo?: string | null;
  periodo_apuracao?: string | null; valor_debito?: string | null; valor_credito?: string | null;
  valor_compensado?: string | null; valor_nao_homologado?: string | null;
  situacao_declaracao?: string | null; situacao_compensacao: string;
  tem_despacho_decisorio?: boolean | null; numero_despacho?: string | null;
  data_despacho?: string | null; tem_intimacao?: boolean | null;
  prazo_resposta_intimacao?: string | null; resultado_analise?: string | null;
  processo_administrativo?: string | null; origem_informacao: string;
  disponibilidade: string; consultado_em?: string | null; observacoes?: string | null;
}

export interface Alerta {
  id: string; cliente_id?: string | null; cliente_razao_social?: string; cliente_cnpj?: string;
  tipo: string; criticidade: "INFO" | "BAIXA" | "MEDIA" | "ALTA" | "CRITICA";
  titulo: string; mensagem: string; explicacao?: string | null;
  evidencias: Record<string, unknown>[]; entidade?: string | null; entidade_id?: string | null;
  status: "NOVO" | "EM_ANALISE" | "RESOLVIDO" | "IGNORADO"; gerado_em: string;
  resolvido_em?: string | null; resolvido_por?: string | null; nota_resolucao?: string | null;
}

export interface Snapshot {
  id: string; cliente_id: string; origem: string; disponibilidade: string;
  situacao_geral: string; total_debitos: string; total_previdenciario: string;
  total_federal: string; total_em_cobranca: string; total_suspenso: string;
  total_parcelado: string; qtd_pendencias: number; qtd_obrigacoes_acessorias: number;
  pendencias: Record<string, string>[]; mensagem?: string | null; consultado_em: string;
  referencia_evento?: string | null;
}

export interface Comparativo {
  id: string; cliente_id: string; snapshot_anterior_id: string; snapshot_atual_id: string;
  total_anterior: string; total_atual: string; diferenca: string;
  novos: Record<string, string>[]; baixados: Record<string, string>[];
  permanecem: Record<string, string>[]; alterados: Record<string, string>[];
  ressalva?: string | null; created_at: string;
}

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) { super(mensagem); }
}

export function obterToken(): string | null { return localStorage.getItem(CHAVE_TOKEN); }
export function obterUsuario(): Usuario | null {
  const bruto = localStorage.getItem(CHAVE_USUARIO);
  return bruto ? (JSON.parse(bruto) as Usuario) : null;
}
export function salvarSessao(token: string, usuario: Usuario) {
  localStorage.setItem(CHAVE_TOKEN, token);
  localStorage.setItem(CHAVE_USUARIO, JSON.stringify(usuario));
}
export function limparSessao() {
  localStorage.removeItem(CHAVE_TOKEN);
  localStorage.removeItem(CHAVE_USUARIO);
}

type Opcoes = { metodo?: string; corpo?: unknown; params?: Record<string, unknown>; arquivo?: FormData };

async function requisicao<T>(caminho: string, opcoes: Opcoes = {}): Promise<T> {
  const url = new URL(`/api${caminho}`, window.location.origin);
  Object.entries(opcoes.params ?? {}).forEach(([chave, valor]) => {
    if (valor !== undefined && valor !== null && valor !== "") url.searchParams.set(chave, String(valor));
  });
  const cabecalhos: Record<string, string> = {};
  const token = obterToken();
  if (token) cabecalhos.Authorization = `Bearer ${token}`;
  let corpo: BodyInit | undefined;
  if (opcoes.arquivo) {
    corpo = opcoes.arquivo;
  } else if (opcoes.corpo !== undefined) {
    cabecalhos["Content-Type"] = "application/json";
    corpo = JSON.stringify(opcoes.corpo);
  }
  const resposta = await fetch(url.toString(), {
    method: opcoes.metodo ?? (corpo ? "POST" : "GET"), headers: cabecalhos, body: corpo,
  });
  if (resposta.status === 401) {
    limparSessao();
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
    throw new ErroApi(401, "Sessão expirada.");
  }
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    try {
      const dados = await resposta.json();
      detalhe = typeof dados.detail === "string" ? dados.detail : JSON.stringify(dados.detail ?? dados);
    } catch { /* corpo não-JSON */ }
    throw new ErroApi(resposta.status, detalhe);
  }
  if (resposta.status === 204) return undefined as T;
  const tipo = resposta.headers.get("content-type") ?? "";
  if (!tipo.includes("application/json")) return (await resposta.blob()) as unknown as T;
  return (await resposta.json()) as T;
}

export const api = {
  get: <T,>(caminho: string, params?: Record<string, unknown>) => requisicao<T>(caminho, { params }),
  post: <T,>(caminho: string, corpo?: unknown, params?: Record<string, unknown>) =>
    requisicao<T>(caminho, { metodo: "POST", corpo, params }),
  patch: <T,>(caminho: string, corpo?: unknown) => requisicao<T>(caminho, { metodo: "PATCH", corpo }),
  delete: <T,>(caminho: string) => requisicao<T>(caminho, { metodo: "DELETE" }),
  upload: <T,>(caminho: string, dados: FormData) => requisicao<T>(caminho, { metodo: "POST", arquivo: dados }),

  async login(email: string, senha: string) {
    const dados = await requisicao<{ access_token: string; usuario: Usuario }>("/auth/login", {
      metodo: "POST", corpo: { email, senha },
    });
    salvarSessao(dados.access_token, dados.usuario);
    return dados.usuario;
  },
};
