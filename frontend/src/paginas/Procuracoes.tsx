import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Aviso, Cartao, Carregando, Kpi, Modal, PontoSemaforo, Selo, Vazio,
} from "../componentes/ui";
import { Pagina, Procuracao, api } from "../lib/api";
import { COR_DISPONIBILIDADE, data, dataHora, rotulo } from "../lib/formato";

interface Painel {
  semaforo: Record<string, number>;
  legenda: Record<string, string>;
  proximos_vencimentos: {
    procuracao_id: string; numero?: string; cliente_id: string; razao_social: string;
    cnpj: string; data_fim: string; dias_para_vencer: number; semaforo: string;
    situacao: string; validada_por_fonte: boolean; disponibilidade: string;
  }[];
  faixas_alerta_dias: number[];
}

interface Consulta {
  id: string; origem: string; disponibilidade: string; situacao_retornada?: string | null;
  data_fim_retornada?: string | null; mensagem?: string | null; consultado_em: string;
}

export default function Procuracoes() {
  const [painel, setPainel] = useState<Painel | null>(null);
  const [lista, setLista] = useState<Pagina<Procuracao> | null>(null);
  const [filtro, setFiltro] = useState({ busca: "", semaforo: "", vence_em_dias: "" });
  const [selecionada, setSelecionada] = useState<Procuracao | null>(null);
  const [consultas, setConsultas] = useState<Consulta[]>([]);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const navegar = useNavigate();

  function carregar() {
    api.get<Painel>("/procuracoes/painel").then(setPainel).catch((e) => setErro(e.message));
    api.get<Pagina<Procuracao>>("/procuracoes", { ...filtro, tamanho: 200 })
      .then(setLista).catch((e) => setErro(e.message));
  }
  useEffect(() => { const t = setTimeout(carregar, 200); return () => clearTimeout(t); }, [filtro]);

  async function abrir(proc: Procuracao) {
    setSelecionada(proc);
    setConsultas(await api.get<Consulta[]>(`/procuracoes/${proc.id}/consultas`));
  }

  async function consultar(proc: Procuracao) {
    try {
      const resposta = await api.post<{ procuracao: Procuracao; consulta: Record<string, unknown> }>(
        `/procuracoes/${proc.id}/consultar`);
      setMensagem(`Consulta registrada: ${resposta.consulta.disponibilidade} · situação ${
        resposta.procuracao.situacao}`);
      await abrir(resposta.procuracao);
      carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha na consulta."); }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!painel) return <Carregando />;

  return (
    <div className="grade">
      {mensagem && <Aviso tipo="ok">{mensagem}</Aviso>}
      <Aviso tipo="info">
        O sistema <b>não presume</b> que uma procuração esteja ativa porque consta na planilha.
        Enquanto não houver validação por fonte autorizada, o semáforo permanece <b>CINZA</b>.
        Faixas de alerta configuradas: {painel.faixas_alerta_dias.join(", ")} dias antes do vencimento.
      </Aviso>

      <div className="grade g4">
        <Kpi rotulo="Verde · ativas" valor={painel.semaforo.VERDE} cor="verde"
             nota={painel.legenda.VERDE} />
        <Kpi rotulo="Amarelo · vencendo" valor={painel.semaforo.AMARELO} cor="amarelo"
             nota={painel.legenda.AMARELO} />
        <Kpi rotulo="Vermelho · expirada/revogada" valor={painel.semaforo.VERMELHO} cor="vermelho"
             nota={painel.legenda.VERMELHO} />
        <Kpi rotulo="Cinza · desconhecida" valor={painel.semaforo.CINZA} cor="cinza"
             nota={painel.legenda.CINZA} />
      </div>

      <Cartao titulo="Próximos vencimentos (janela de -30 a +60 dias)" semPadding>
        {painel.proximos_vencimentos.length === 0 ? <Vazio>Nenhum vencimento na janela.</Vazio> : (
          <table>
            <thead><tr><th /><th>Cliente</th><th>Procuração</th><th>Validade</th>
                        <th className="num">Dias</th><th>Situação</th><th>Validada</th></tr></thead>
            <tbody>
              {painel.proximos_vencimentos.map((p) => (
                <tr key={p.procuracao_id} className="clicavel"
                    onClick={() => navegar(`/clientes/${p.cliente_id}`)}>
                  <td><PontoSemaforo valor={p.semaforo} /></td>
                  <td><b style={{ color: "var(--marinho)" }}>{p.razao_social}</b>
                      <div className="mono" style={{ fontSize: 11, color: "var(--cinza-500)" }}>{p.cnpj}</div></td>
                  <td className="mono">{p.numero ?? "—"}</td>
                  <td>{data(p.data_fim)}</td>
                  <td className="num" style={{ color: p.dias_para_vencer < 0 ? "var(--vermelho)" : undefined }}>
                    {p.dias_para_vencer}</td>
                  <td>{rotulo(p.situacao)}</td>
                  <td>{p.validada_por_fonte ? <Selo cor="verde">Sim</Selo>
                    : <Selo cor="cinza">{rotulo(p.disponibilidade)}</Selo>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      <Cartao titulo="Todas as procurações" semPadding>
        <div className="filtros" style={{ padding: 16, borderBottom: "1px solid var(--cinza-100)" }}>
          <div className="campo" style={{ flex: 1, minWidth: 240 }}>
            <label>Buscar</label>
            <input placeholder="Cliente, CNPJ ou número" value={filtro.busca}
                   onChange={(e) => setFiltro({ ...filtro, busca: e.target.value })} />
          </div>
          <div className="campo">
            <label>Semáforo</label>
            <select value={filtro.semaforo} onChange={(e) => setFiltro({ ...filtro, semaforo: e.target.value })}>
              <option value="">Todos</option>
              {["VERDE", "AMARELO", "VERMELHO", "CINZA"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="campo">
            <label>Vence em até (dias)</label>
            <input type="number" min={0} value={filtro.vence_em_dias}
                   onChange={(e) => setFiltro({ ...filtro, vence_em_dias: e.target.value })} />
          </div>
        </div>
        {!lista ? <Carregando /> : lista.itens.length === 0 ? <Vazio>Nada encontrado.</Vazio> : (
          <table>
            <thead><tr><th /><th>Cliente</th><th>Número</th><th>Procurador</th><th>Início</th>
                        <th>Validade</th><th>Situação</th><th>Declarada</th><th>Fonte</th><th /></tr></thead>
            <tbody>
              {lista.itens.map((p) => (
                <tr key={p.id}>
                  <td><PontoSemaforo valor={p.semaforo ?? "CINZA"} /></td>
                  <td><b style={{ color: "var(--marinho)" }}>{p.cliente_razao_social}</b>
                      <div className="mono" style={{ fontSize: 11, color: "var(--cinza-500)" }}>
                        {p.cliente_cnpj}</div></td>
                  <td className="mono">{p.numero ?? "—"}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{p.procurador_doc ?? "—"}</td>
                  <td>{data(p.data_inicio)}</td>
                  <td>{data(p.data_fim)}</td>
                  <td>{rotulo(p.situacao)}</td>
                  <td style={{ fontSize: 12, color: "var(--cinza-500)" }}>{rotulo(p.situacao_declarada)}</td>
                  <td style={{ fontSize: 11 }}>
                    <Selo cor={COR_DISPONIBILIDADE[p.disponibilidade]}>{rotulo(p.disponibilidade)}</Selo>
                    <div style={{ color: "var(--cinza-500)" }}>{dataHora(p.consultado_em)}</div>
                  </td>
                  <td><button className="link pequeno" onClick={() => abrir(p)}>Detalhes</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      {selecionada && (
        <Modal titulo={`Procuração ${selecionada.numero ?? selecionada.id.slice(0, 8)}`}
               aoFechar={() => setSelecionada(null)}>
          <div className="lista-definicoes">
            <div><span>Cliente</span><b>{selecionada.cliente_razao_social}</b></div>
            <div><span>CNPJ outorgante</span><b className="mono">{selecionada.cliente_cnpj}</b></div>
            <div><span>Procurador</span><b className="mono">{selecionada.procurador_doc ?? "—"}</b></div>
            <div><span>Início</span><b>{data(selecionada.data_inicio)}</b></div>
            <div><span>Validade</span><b>{data(selecionada.data_fim)}</b></div>
            <div><span>Dias para vencer</span><b>{selecionada.dias_para_vencer ?? "—"}</b></div>
            <div><span>Situação (sistema)</span><b>{rotulo(selecionada.situacao)}</b></div>
            <div><span>Situação declarada</span><b>{rotulo(selecionada.situacao_declarada)}</b></div>
            <div><span>Validada por fonte</span><b>{selecionada.validada_por_fonte ? "Sim" : "Não"}</b></div>
            <div><span>Disponibilidade</span><b>{rotulo(selecionada.disponibilidade)}</b></div>
          </div>

          {selecionada.poderes && selecionada.poderes.length > 0 && (
            <div className="espaco">
              <h3>Poderes / serviços autorizados</h3>
              <div className="linha" style={{ marginTop: 8 }}>
                {selecionada.poderes.map((p) => <Selo key={p} cor="azul">{p}</Selo>)}
                {(selecionada.servicos_autorizados ?? []).map((s) => <Selo key={s} cor="cinza">{s}</Selo>)}
              </div>
            </div>
          )}

          <div className="espaco linha">
            <button className="primario pequeno" onClick={() => consultar(selecionada)}>
              Consultar fonte agora
            </button>
          </div>

          <div className="espaco">
            <h3>Histórico de consultas</h3>
            <ul className="timeline" style={{ marginTop: 12 }}>
              {consultas.map((c) => (
                <li key={c.id}>
                  <div className="quando">{dataHora(c.consultado_em)} · {c.origem}</div>
                  <b>{rotulo(c.disponibilidade)}</b>
                  {c.situacao_retornada && <div style={{ fontSize: 12 }}>
                    Situação retornada: {rotulo(c.situacao_retornada)}
                    {c.data_fim_retornada ? ` · validade ${data(c.data_fim_retornada)}` : ""}
                  </div>}
                  {c.mensagem && <div style={{ fontSize: 12, color: "var(--cinza-500)" }}>{c.mensagem}</div>}
                </li>
              ))}
            </ul>
          </div>
        </Modal>
      )}
    </div>
  );
}
