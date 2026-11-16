/**
 * Teste de ponta a ponta da interface (Playwright + Chromium).
 *
 *   node e2e/fluxo-ui.mjs [URL_BASE]
 *
 * Percorre: login -> painel -> clientes -> ficha do cliente -> compensações ->
 * procurações -> situação fiscal -> alertas -> monitoramento -> fontes ->
 * auditoria, verificando conteúdo real em cada tela e salvando capturas em
 * e2e/capturas/.
 */
import { createRequire } from "node:module";
// O Chromium/Playwright já instalados no ambiente são resolvidos via require,
// evitando dependência local no pacote.
const exigir = createRequire(import.meta.url);
const { chromium } = exigir(process.env.PLAYWRIGHT_PATH ?? "playwright");
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.argv[2] ?? "http://127.0.0.1:8000";
const AQUI = dirname(fileURLToPath(import.meta.url));
const CAPTURAS = join(AQUI, "capturas");
mkdirSync(CAPTURAS, { recursive: true });

const resultados = [];
let falhas = 0;

async function etapa(nome, fn) {
  try {
    await fn();
    resultados.push({ nome, status: "OK" });
    console.log(`  ok   ${nome}`);
  } catch (erro) {
    falhas += 1;
    resultados.push({ nome, status: "FALHOU", erro: String(erro.message ?? erro) });
    console.log(`  FALHOU ${nome}: ${erro.message ?? erro}`);
  }
}

function confirmar(condicao, mensagem) {
  if (!condicao) throw new Error(mensagem);
}

const navegador = await chromium.launch({ args: ["--no-sandbox"] });
const contexto = await navegador.newContext({ viewport: { width: 1480, height: 1000 }, deviceScaleFactor: 1 });
const pagina = await contexto.newPage();
const errosConsole = [];
pagina.on("console", (m) => { if (m.type() === "error") errosConsole.push(m.text()); });

async function capturar(nome) {
  await pagina.screenshot({ path: join(CAPTURAS, `${nome}.png`), fullPage: true });
}

console.log(`Executando fluxo de UI em ${BASE}`);

await etapa("tela de login é exibida", async () => {
  await pagina.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  confirmar(await pagina.getByRole("heading", { name: "Entrar" }).isVisible(), "título 'Entrar' ausente");
  await capturar("01-login");
});

await etapa("login com credenciais de demonstração", async () => {
  await pagina.fill("#email", "admin@monitortributario.com.br");
  await pagina.fill("#senha", "Admin@123456");
  await pagina.getByRole("button", { name: "Entrar" }).click();
  await pagina.waitForURL(`${BASE}/`, { timeout: 15000 });
  await pagina.waitForSelector(".kpi .valor");
});

await etapa("painel mostra indicadores e aviso de modo demonstração", async () => {
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Clientes cadastrados"), "KPI de clientes ausente");
  confirmar(texto.includes("Compensações monitoradas"), "KPI de compensações ausente");
  confirmar(texto.includes("Procurações ativas"), "KPI de procurações ausente");
  confirmar(texto.includes("Modo demonstração"), "aviso de simulador ausente");
  confirmar(texto.includes("Clientes que exigem atenção"), "ranking de atenção ausente");
  await pagina.waitForSelector(".recharts-surface");
  await capturar("02-painel");
});

await etapa("lista de clientes carrega 10 empresas demonstrativas", async () => {
  await pagina.locator(".nav-item").filter({ hasText: "Clientes" }).first().click();
  await pagina.waitForSelector("tbody tr");
  const linhas = await pagina.locator("tbody tr").count();
  confirmar(linhas >= 10, `esperado >= 10 clientes, obtido ${linhas}`);
  await capturar("03-clientes");
});

await etapa("ficha do cliente traz procurações, PER/DCOMP e resumo", async () => {
  await pagina.locator("tbody tr").first().click();
  await pagina.waitForSelector("h2");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Resumo interpretado"), "resumo da IA ausente");
  confirmar(texto.includes("Procurações eletrônicas"), "bloco de procurações ausente");
  confirmar(texto.includes("Compensações (PER/DCOMP)"), "bloco de PER/DCOMP ausente");
  confirmar(texto.includes("Limites da interpretação"), "limites da IA ausentes");
  await capturar("04-cliente-detalhe");
});

await etapa("compensações listam classificações e situações", async () => {
  await pagina.getByRole("button", { name: "Compensações" }).click();
  await pagina.waitForSelector("tbody tr");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Classificações usadas pelo sistema"), "classificações ausentes");
  confirmar(texto.includes("Sem informacao") || texto.includes("Sem informação"),
    "classificação 'sem informação' ausente");
  await capturar("05-compensacoes");
});

await etapa("detalhe de PER/DCOMP abre histórico de evolução", async () => {
  await pagina.locator("tbody tr").first().click();
  await pagina.waitForSelector(".modal");
  const texto = await pagina.textContent(".modal");
  confirmar(texto.includes("Histórico de evolução"), "linha do tempo ausente");
  confirmar(texto.includes("Registrar resultado oficial manualmente"), "registro manual ausente");
  await capturar("06-perdcomp-detalhe");
  await pagina.locator(".modal header button").click();
});

await etapa("painel de procurações aplica semáforo", async () => {
  await pagina.getByRole("button", { name: "Procurações" }).click();
  await pagina.waitForSelector(".kpi");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Verde · ativas"), "KPI verde ausente");
  confirmar(texto.includes("Cinza · desconhecida"), "KPI cinza ausente");
  confirmar(texto.includes("não presume"), "aviso de não presunção ausente");
  const pontos = await pagina.locator(".ponto").count();
  confirmar(pontos > 0, "nenhum indicador de semáforo renderizado");
  await capturar("07-procuracoes");
});

await etapa("situação fiscal mostra variação entre consultas", async () => {
  await pagina.getByRole("button", { name: "Situação fiscal" }).click();
  await pagina.waitForSelector("tbody tr");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("snapshot"), "explicação de snapshot ausente");
  confirmar(texto.includes("Variação") || texto.includes("Total atual"), "colunas de comparação ausentes");
  await capturar("08-situacao-fiscal");
});

await etapa("alerta exibe explicação e evidências", async () => {
  await pagina.getByRole("button", { name: "Alertas" }).click();
  await pagina.waitForSelector("tbody tr");
  await pagina.locator("tbody tr").first().click();
  await pagina.waitForSelector(".modal");
  const texto = await pagina.textContent(".modal");
  confirmar(texto.includes("Por que este alerta foi gerado"), "explicação ausente");
  confirmar(texto.includes("Evidências"), "evidências ausentes");
  confirmar(texto.toLowerCase().includes("consultado em"), "data da consulta ausente nas evidências");
  await capturar("09-alerta-detalhe");
  await pagina.locator(".modal header button").click();
});

await etapa("monitoramento mostra agendador, regras e simulador", async () => {
  await pagina.getByRole("button", { name: "Execuções e regras" }).click();
  await pagina.waitForSelector("tbody tr");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Simulador de mudanças"), "simulador ausente");
  confirmar(texto.includes("Regras de monitoramento"), "regras ausentes");
  confirmar(texto.includes("Execuções recentes"), "execuções ausentes");
  await capturar("10-monitoramento");
});

await etapa("executa monitoramento pela interface", async () => {
  await pagina.getByRole("button", { name: "Executar", exact: true }).click();
  await pagina.waitForSelector(".aviso.ok", { timeout: 60000 });
  const texto = await pagina.textContent(".aviso.ok");
  confirmar(texto.includes("consulta"), `mensagem inesperada: ${texto}`);
  await capturar("11-execucao-realizada");
});

await etapa("fontes de dados declaram limitações", async () => {
  await pagina.getByRole("button", { name: "Fontes de dados" }).click();
  await pagina.waitForSelector(".cartao");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Limitações declaradas"), "limitações ausentes");
  confirmar(texto.includes("Integra Contador"), "bloco do Integra Contador ausente");
  confirmar(texto.includes("Regras de ouro"), "regras de ouro ausentes");
  await capturar("12-fontes");
});

await etapa("auditoria registra as ações da sessão", async () => {
  await pagina.getByRole("button", { name: "Auditoria" }).click();
  await pagina.waitForSelector("tbody tr");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Login") || texto.includes("LOGIN"), "registro de login ausente");
  confirmar(texto.includes("Monitoramento"), "registro de monitoramento ausente");
  await capturar("13-auditoria");
});

await etapa("importação exibe assistente e modelo", async () => {
  await pagina.getByRole("button", { name: "Importar planilha" }).click();
  await pagina.waitForSelector("input[type=file]");
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("Campos reconhecidos automaticamente"), "lista de campos ausente");
  confirmar(texto.includes("Importações anteriores"), "histórico de importações ausente");
  await capturar("14-importacao");
});

await etapa("importa a planilha de teste pela interface", async () => {
  await pagina.setInputFiles("input[type=file]",
    join(AQUI, "..", "data", "planilha-teste-clientes.xlsx"));
  await pagina.waitForSelector("text=Colunas detectadas", { timeout: 30000 });
  const texto = await pagina.textContent("main");
  confirmar(texto.includes("→ cnpj"), "mapeamento de CNPJ não exibido");
  confirmar(texto.includes("Com erro: 1"), "linha com CNPJ inválido não sinalizada");
  confirmar(texto.includes("Duplicadas: 1"), "linha duplicada não sinalizada");
  await capturar("15-importacao-validacao");
});

await etapa("sem erros de console no fluxo", async () => {
  const relevantes = errosConsole.filter((e) => !e.includes("favicon"));
  confirmar(relevantes.length === 0, `erros de console: ${relevantes.join(" | ")}`);
});

await navegador.close();

console.log("\n=== Resultado ===");
for (const r of resultados) {
  console.log(`${r.status.padEnd(7)} ${r.nome}${r.erro ? ` -> ${r.erro}` : ""}`);
}
console.log(`\n${resultados.length - falhas}/${resultados.length} etapas OK. Capturas em ${CAPTURAS}`);
process.exit(falhas === 0 ? 0 : 1);
