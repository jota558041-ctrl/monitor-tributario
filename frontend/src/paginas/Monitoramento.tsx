import { useEffect, useState } from "react";
import { Aviso, Cartao, Carregando, Selo, Vazio } from "../componentes/ui";
import { Cliente, Pagina, Perfil, api } from "../lib/api";
import { dataHora, rotulo } from "../lib/formato";

interface Execucao {
  id: string; tipo: string; status: string; acionada_por: string; total_clientes: number;
  consultas_ok: number; consultas_indisponiveis: number; consultas_nao_autorizadas: number;
  alertas_gerados: number; mudancas_detectadas: number; iniciado_em: string;
  finalizado_em?: string | null;
}
interface Regra {
  id: string; nome: string; tipo_monitoramento: string; ativo: boolean; cron: string;
  criticidade_minima: string; canais: string[]; destinatarios?: string[] | null;
  ultima_execucao?: string | null; proxima_execucao?: string | null;
}
interface Agendamento {
  ativo: boolean; timezone: string; motivo?: string;
  jobs: { id: string; nome: string; proxima_execucao?: string | null; gatilho: string }[];
}
interface Cenario { cenario: string; descricao: string }
interface Notificacao {
  id: string; canal: string; destinatario?: string | null; status: string;
  assunto?: string | null; enviada_em?: string | null; created_at: string;
}

const TIPOS = ["COMPLETO", "PROCURACOES", "COMPENSACOES", "SITUACAO_FISCAL"];

export default function Monitoramento({ perfil }: { perfil: Perfil }) {
  const [execucoes, setExecucoes] = useState<Execucao[] | null>(null);
  const [regras, setRegras] = useState<Regra[]>([]);
  const [agendamento, setAgendamento] = useState<Agendamento | null>(null);
  const [cenarios, setCenarios] = useState<Cenario[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);
  const [tipo, setTipo] = useState("COMPLETO");
  const [clienteAlvo, setClienteAlvo] = useState("");
  const [cenario, setCenario] = useState("");
  const [executando, setExecutando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [novaRegra, setNovaRegra] = useState({ nome: "", tipo_monitoramento: "COMPLETO",
    cron: "0 6 * * *", criticidade_minima: "BAIXA", canais: ["SISTEMA"] as string[] });

  function carregar() {
    api.get<Execucao[]>("/monitoramento/execucoes", { limite: 25 }).then(setExecucoes).catch(() => {});
    api.get<Regra[]>("/regras").then(setRegras).catch(() => {});
    api.get<Agendamento>("/monitoramento/agendamento").then(setAgendamento).catch(() => {});
    api.get<Pagina<Notificacao>>("/notificacoes", { tamanho: 15 })
      .then((d) => setNotificacoes(d.itens)).catch(() => {});
  }

  useEffect(() => {
    carregar();
    api.get<Cenario[]>("/simulacao/cenarios").then(setCenarios).catch(() => {});
    api.get<Pagina<Cliente>>("/clientes", { tamanho: 200 })
      .then((d) => setClientes(d.itens)).catch(() => {});
  }, []);

  async function executar() {
    setExecutando(true); setErro(null); setMensagem(null);
    try {
      const resposta = await api.post<{ execucao: Execucao }>("/monitoramento/executar", {
        tipo, clientes_ids: clienteAlvo ? [clienteAlvo] : undefined,
      });
      const e = resposta.execucao;
      setMensagem(`Execução ${e.status}: ${e.total_clientes} cliente(s), ${e.consultas_ok} consulta(s) OK, ` +
        `${e.consultas_indisponiveis} indisponível(is), ${e.consultas_nao_autorizadas} sem autorização, ` +
        `${e.mudancas_detectadas} mudança(s), ${e.alertas_gerados} alerta(s) novo(s).`);
      carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha na execução."); }
    finally { setExecutando(false); }
  }

  async function aplicarCenario() {
    if (!clienteAlvo || !cenario) { setErro("Selecione cliente e cenário."); return; }
    setErro(null);
    try {
      const resposta = await api.post<{ mudancas: string[]; proximo_passo: string }>(
        "/simulacao/aplicar", { cliente_id: clienteAlvo, cenario });
      setMensagem(`${resposta.mudancas.join(" ")} ${resposta.proximo_passo}`);
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao aplicar cenário."); }
  }

  async function criarRegra() {
    try {
      await api.post("/regras", novaRegra);
      setNovaRegra({ ...novaRegra, nome: "" });
      carregar();
      setMensagem("Regra criada e agendada.");
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao criar regra."); }
  }

  async function alternarRegra(regra: Regra) {
    await api.patch(`/regras/${regra.id}`, { ativo: !regra.ativo });
    carregar();
  }

  return (
    <div className="grade">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {mensagem && <Aviso tipo="ok">{mensagem}</Aviso>}

      <div className="grade g2">
        <Cartao titulo="Executar monitoramento agora"
                descricao="Consulta as fontes configuradas, grava histórico e gera alertas">
          <div className="grade g3">
            <div>
              <label>Tipo</label>
              <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
                {TIPOS.map((t) => <option key={t} value={t}>{rotulo(t)}</option>)}
              </select>
            </div>
            <div>
              <label>Cliente (opcional)</label>
              <select value={clienteAlvo} onChange={(e) => setClienteAlvo(e.target.value)}>
                <option value="">Todos os clientes ativos</option>
                {clientes.map((c) => <option key={c.id} value={c.id}>{c.razao_social}</option>)}
              </select>
            </div>
          </div>
          <div className="espaco">
            <button className="primario" onClick={executar} disabled={executando}>
              {executando ? <span className="carregando" /> : null} Executar
            </button>
          </div>
        </Cartao>

        <Cartao titulo="Simulador de mudanças"
                descricao="Altera o 'mundo fiscal' fictício para verificar se os alertas disparam">
          <div className="grade g2">
            <div>
              <label>Cliente</label>
              <select value={clienteAlvo} onChange={(e) => setClienteAlvo(e.target.value)}>
                <option value="">Selecione…</option>
                {clientes.map((c) => <option key={c.id} value={c.id}>{c.razao_social}</option>)}
              </select>
            </div>
            <div>
              <label>Cenário</label>
              <select value={cenario} onChange={(e) => setCenario(e.target.value)}>
                <option value="">Selecione…</option>
                {cenarios.map((c) => <option key={c.cenario} value={c.cenario}>{rotulo(c.cenario)}</option>)}
              </select>
            </div>
          </div>
          {cenario && (
            <div className="espaco" style={{ fontSize: 12, color: "var(--cinza-500)" }}>
              {cenarios.find((c) => c.cenario === cenario)?.descricao}
            </div>
          )}
          <div className="espaco linha">
            <button className="azul" onClick={aplicarCenario}>Aplicar cenário</button>
            <button onClick={executar} disabled={executando}>Depois, executar monitoramento</button>
          </div>
        </Cartao>
      </div>

      <Cartao titulo="Agendador"
              descricao={agendamento?.ativo
                ? `Ativo · fuso ${agendamento.timezone}`
                : `Inativo · ${agendamento?.motivo ?? ""}`} semPadding>
        {!agendamento || agendamento.jobs.length === 0 ? (
          <Vazio>Nenhum job agendado.</Vazio>
        ) : (
          <table>
            <thead><tr><th>Job</th><th>Próxima execução</th><th>Gatilho</th></tr></thead>
            <tbody>
              {agendamento.jobs.map((j) => (
                <tr key={j.id}>
                  <td>{j.nome}</td>
                  <td>{dataHora(j.proxima_execucao)}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{j.gatilho}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      <Cartao titulo="Regras de monitoramento" semPadding
              descricao="Frequência, escopo, criticidade mínima e canais de notificação">
        <table>
          <thead><tr><th>Nome</th><th>Tipo</th><th>Cron</th><th>Criticidade mín.</th>
                      <th>Canais</th><th>Última</th><th>Próxima</th><th>Status</th><th /></tr></thead>
          <tbody>
            {regras.map((r) => (
              <tr key={r.id}>
                <td><b style={{ color: "var(--marinho)" }}>{r.nome}</b></td>
                <td>{rotulo(r.tipo_monitoramento)}</td>
                <td className="mono">{r.cron}</td>
                <td>{r.criticidade_minima}</td>
                <td style={{ fontSize: 11 }}>{r.canais.join(", ")}
                  {r.destinatarios && r.destinatarios.length > 0 && (
                    <div style={{ color: "var(--cinza-500)" }}>{r.destinatarios.join(", ")}</div>
                  )}</td>
                <td style={{ fontSize: 12 }}>{dataHora(r.ultima_execucao)}</td>
                <td style={{ fontSize: 12 }}>{dataHora(r.proxima_execucao)}</td>
                <td>{r.ativo ? <Selo cor="verde">Ativa</Selo> : <Selo cor="cinza">Pausada</Selo>}</td>
                <td>{perfil === "ADMIN" && (
                  <button className="link pequeno" onClick={() => alternarRegra(r)}>
                    {r.ativo ? "Pausar" : "Ativar"}
                  </button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {perfil === "ADMIN" && (
          <div style={{ padding: 16, borderTop: "1px solid var(--cinza-100)" }}>
            <h3>Nova regra</h3>
            <div className="grade g4" style={{ marginTop: 10 }}>
              <div>
                <label>Nome</label>
                <input value={novaRegra.nome} placeholder="Ex.: Compensações 3x ao dia"
                       onChange={(e) => setNovaRegra({ ...novaRegra, nome: e.target.value })} />
              </div>
              <div>
                <label>Tipo</label>
                <select value={novaRegra.tipo_monitoramento}
                        onChange={(e) => setNovaRegra({ ...novaRegra, tipo_monitoramento: e.target.value })}>
                  {TIPOS.map((t) => <option key={t} value={t}>{rotulo(t)}</option>)}
                </select>
              </div>
              <div>
                <label>Cron (min hora dia mês dia-sem)</label>
                <input className="mono" value={novaRegra.cron}
                       onChange={(e) => setNovaRegra({ ...novaRegra, cron: e.target.value })} />
              </div>
              <div>
                <label>Criticidade mínima</label>
                <select value={novaRegra.criticidade_minima}
                        onChange={(e) => setNovaRegra({ ...novaRegra, criticidade_minima: e.target.value })}>
                  {["INFO", "BAIXA", "MEDIA", "ALTA", "CRITICA"].map((c) =>
                    <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div className="espaco linha">
              <label style={{ margin: 0 }}>
                <input type="checkbox" style={{ width: "auto", marginRight: 6 }}
                       checked={novaRegra.canais.includes("EMAIL")}
                       onChange={(e) => setNovaRegra({
                         ...novaRegra,
                         canais: e.target.checked ? ["SISTEMA", "EMAIL"] : ["SISTEMA"],
                       })} />
                Também notificar por e-mail
              </label>
              <button className="primario" onClick={criarRegra} disabled={!novaRegra.nome}>
                Criar regra
              </button>
            </div>
          </div>
        )}
      </Cartao>

      <div className="grade g2">
        <Cartao titulo="Execuções recentes" semPadding>
          {!execucoes ? <Carregando /> : execucoes.length === 0 ? <Vazio>Nenhuma execução.</Vazio> : (
            <table>
              <thead><tr><th>Início</th><th>Tipo</th><th>Acionada por</th><th className="num">Clientes</th>
                          <th className="num">OK</th><th className="num">Indisp.</th>
                          <th className="num">Mudanças</th><th className="num">Alertas</th>
                          <th>Status</th></tr></thead>
              <tbody>
                {execucoes.map((e) => (
                  <tr key={e.id}>
                    <td style={{ fontSize: 12 }}>{dataHora(e.iniciado_em)}</td>
                    <td style={{ fontSize: 12 }}>{rotulo(e.tipo)}</td>
                    <td style={{ fontSize: 11 }}>{e.acionada_por}</td>
                    <td className="num">{e.total_clientes}</td>
                    <td className="num">{e.consultas_ok}</td>
                    <td className="num">{e.consultas_indisponiveis + e.consultas_nao_autorizadas}</td>
                    <td className="num">{e.mudancas_detectadas}</td>
                    <td className="num">{e.alertas_gerados}</td>
                    <td><Selo cor={e.status === "CONCLUIDA" ? "verde"
                      : e.status === "FALHOU" ? "vermelho" : "amarelo"}>
                      {rotulo(e.status)}</Selo></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>

        <Cartao titulo="Notificações registradas" semPadding
                descricao="Todo alerta gera registro; e-mail depende de MT_EMAIL_ENABLED">
          {notificacoes.length === 0 ? <Vazio>Nenhuma notificação.</Vazio> : (
            <table>
              <thead><tr><th>Assunto</th><th>Canal</th><th>Destinatário</th><th>Status</th><th>Quando</th></tr></thead>
              <tbody>
                {notificacoes.map((n) => (
                  <tr key={n.id}>
                    <td style={{ fontSize: 12 }}>{n.assunto}</td>
                    <td>{n.canal}</td>
                    <td style={{ fontSize: 12 }}>{n.destinatario ?? "—"}</td>
                    <td><Selo cor={n.status === "ENVIADA" ? "verde" : n.status === "ERRO" ? "vermelho" : "cinza"}>
                      {rotulo(n.status)}</Selo></td>
                    <td style={{ fontSize: 12 }}>{dataHora(n.enviada_em ?? n.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>
      </div>
    </div>
  );
}
