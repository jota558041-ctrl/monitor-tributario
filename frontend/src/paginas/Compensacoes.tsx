import { useEffect, useState } from "react";
import {
  Aviso, Cartao, Carregando, Definicoes, Modal, Paginacao, Selo, Vazio,
} from "../componentes/ui";
import { Compensacao, Pagina, api } from "../lib/api";
import {
  COR_DISPONIBILIDADE, COR_SITUACAO_COMPENSACAO, brl, cnpj as fmtCnpj, data, dataHora, rotulo,
} from "../lib/formato";

interface Evento {
  id: string; tipo: string; situacao_anterior?: string | null; situacao_nova?: string | null;
  origem: string; disponibilidade?: string | null; mensagem?: string | null;
  payload?: Record<string, unknown> | null; registrado_em: string; criado_por?: string | null;
}

const SITUACOES = ["TRANSMITIDA", "EM_PROCESSAMENTO", "EM_ANALISE", "HOMOLOGADA",
  "NAO_HOMOLOGADA", "HOMOLOGADA_PARCIALMENTE", "CANCELADA", "COM_EXIGENCIA", "SEM_INFORMACAO"];

export default function Compensacoes() {
  const [dados, setDados] = useState<Pagina<Compensacao> | null>(null);
  const [classificacoes, setClassificacoes] = useState<{ codigo: string; descricao: string }[]>([]);
  const [tributos, setTributos] = useState<string[]>([]);
  const [filtros, setFiltros] = useState({ busca: "", situacao: "", tributo: "", data_inicio: "", data_fim: "" });
  const [pagina, setPagina] = useState(1);
  const [selecionada, setSelecionada] = useState<Compensacao | null>(null);
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [manual, setManual] = useState({ situacao_compensacao: "HOMOLOGADA", numero_despacho: "",
    valor_nao_homologado: "", resultado_analise: "" });
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ codigo: string; descricao: string }[]>("/compensacoes/classificacoes")
      .then(setClassificacoes).catch(() => {});
    api.get<string[]>("/compensacoes/tributos").then(setTributos).catch(() => {});
  }, []);

  function carregar() {
    api.get<Pagina<Compensacao>>("/compensacoes", { ...filtros, pagina, tamanho: 25 })
      .then(setDados).catch((e) => setErro(e.message));
  }
  useEffect(() => { const t = setTimeout(carregar, 250); return () => clearTimeout(t); },
    [filtros, pagina]);

  async function abrir(comp: Compensacao) {
    setSelecionada(comp);
    setEventos(await api.get<Evento[]>(`/compensacoes/${comp.id}/historico`));
  }

  async function consultar(comp: Compensacao) {
    try {
      const resposta = await api.post<{ compensacao: Compensacao; consulta: Record<string, unknown> }>(
        `/compensacoes/${comp.id}/consultar`);
      setMensagem(`Consulta registrada: ${resposta.consulta.disponibilidade} · situação ${
        resposta.compensacao.situacao_compensacao}`);
      await abrir(resposta.compensacao);
      carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha na consulta."); }
  }

  async function registrarManual() {
    if (!selecionada) return;
    try {
      const corpo: Record<string, unknown> = {
        situacao_compensacao: manual.situacao_compensacao,
        resultado_analise: manual.resultado_analise || undefined,
        numero_despacho: manual.numero_despacho || undefined,
        tem_despacho_decisorio: Boolean(manual.numero_despacho) || undefined,
        valor_nao_homologado: manual.valor_nao_homologado || undefined,
      };
      const resposta = await api.post<{ compensacao: Compensacao }>(
        `/compensacoes/${selecionada.id}/resultado-manual`, corpo);
      setMensagem("Resultado oficial registrado manualmente (origem IMPORTACAO_RELATORIO).");
      await abrir(resposta.compensacao);
      carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao registrar."); }
  }

  return (
    <div className="grade">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {mensagem && <Aviso tipo="ok">{mensagem}</Aviso>}

      <Cartao titulo="Classificações usadas pelo sistema"
              descricao="Transmissão não equivale a homologação; ausência de informação não equivale a deferimento">
        <div className="linha">
          {classificacoes.map((c) => (
            <Selo key={c.codigo} cor={COR_SITUACAO_COMPENSACAO[c.codigo]} titulo={c.descricao}>
              {rotulo(c.codigo)}
            </Selo>
          ))}
        </div>
      </Cartao>

      <Cartao titulo="Compensações monitoradas" semPadding>
        <div className="filtros" style={{ padding: 16, borderBottom: "1px solid var(--cinza-100)" }}>
          <div className="campo" style={{ flex: 1, minWidth: 240 }}>
            <label>Buscar</label>
            <input placeholder="PER/DCOMP, CNPJ ou razão social" value={filtros.busca}
                   onChange={(e) => { setFiltros({ ...filtros, busca: e.target.value }); setPagina(1); }} />
          </div>
          <div className="campo">
            <label>Situação</label>
            <select value={filtros.situacao}
                    onChange={(e) => { setFiltros({ ...filtros, situacao: e.target.value }); setPagina(1); }}>
              <option value="">Todas</option>
              {SITUACOES.map((s) => <option key={s} value={s}>{rotulo(s)}</option>)}
            </select>
          </div>
          <div className="campo">
            <label>Tributo</label>
            <select value={filtros.tributo}
                    onChange={(e) => { setFiltros({ ...filtros, tributo: e.target.value }); setPagina(1); }}>
              <option value="">Todos</option>
              {tributos.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="campo">
            <label>Transmissão de</label>
            <input type="date" value={filtros.data_inicio}
                   onChange={(e) => setFiltros({ ...filtros, data_inicio: e.target.value })} />
          </div>
          <div className="campo">
            <label>até</label>
            <input type="date" value={filtros.data_fim}
                   onChange={(e) => setFiltros({ ...filtros, data_fim: e.target.value })} />
          </div>
        </div>

        {!dados ? <Carregando /> : dados.itens.length === 0 ? (
          <Vazio>Nenhuma compensação encontrada.</Vazio>
        ) : (
          <>
            <table>
              <thead>
                <tr><th>PER/DCOMP</th><th>Cliente</th><th>Tributo</th><th>PA</th>
                    <th>Transmissão</th><th className="num">Crédito</th><th>Situação</th>
                    <th>Despacho/Intimação</th><th>Fonte</th></tr>
              </thead>
              <tbody>
                {dados.itens.map((c) => (
                  <tr key={c.id} className="clicavel" onClick={() => abrir(c)}>
                    <td className="mono" style={{ fontSize: 11 }}>{c.numero_perdcomp}</td>
                    <td>
                      <b style={{ color: "var(--marinho)" }}>{c.cliente_razao_social}</b>
                      <div className="mono" style={{ fontSize: 11, color: "var(--cinza-500)" }}>
                        {c.cliente_cnpj}
                      </div>
                    </td>
                    <td>{c.tributo ?? "—"}</td>
                    <td>{c.periodo_apuracao ?? "—"}</td>
                    <td>{data(c.data_transmissao)}</td>
                    <td className="num">{brl(c.valor_credito)}</td>
                    <td><Selo cor={COR_SITUACAO_COMPENSACAO[c.situacao_compensacao]}>
                      {rotulo(c.situacao_compensacao)}</Selo></td>
                    <td style={{ fontSize: 11 }}>
                      {c.tem_despacho_decisorio ? <Selo cor="azul">Despacho</Selo> : null}{" "}
                      {c.tem_intimacao ? <Selo cor="vermelho">Intimação</Selo> : null}
                      {!c.tem_despacho_decisorio && !c.tem_intimacao ? "—" : null}
                    </td>
                    <td style={{ fontSize: 11 }}>
                      <Selo cor={COR_DISPONIBILIDADE[c.disponibilidade]}>{rotulo(c.disponibilidade)}</Selo>
                      <div style={{ color: "var(--cinza-500)" }}>{dataHora(c.consultado_em)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginacao pagina={dados.pagina} total={dados.total} tamanho={dados.tamanho} aoMudar={setPagina} />
          </>
        )}
      </Cartao>

      {selecionada && (
        <Modal titulo={`PER/DCOMP ${selecionada.numero_perdcomp}`} aoFechar={() => setSelecionada(null)}>
          <Definicoes itens={[
            ["Cliente", selecionada.cliente_razao_social],
            ["CNPJ", selecionada.cliente_cnpj ?? fmtCnpj(selecionada.cliente_cnpj)],
            ["Tributo", selecionada.tributo],
            ["Período de apuração", selecionada.periodo_apuracao],
            ["Data de transmissão", data(selecionada.data_transmissao)],
            ["Valor do débito", brl(selecionada.valor_debito)],
            ["Crédito utilizado", brl(selecionada.valor_credito)],
            ["Valor compensado", selecionada.valor_compensado ? brl(selecionada.valor_compensado) : "—"],
            ["Valor não homologado", selecionada.valor_nao_homologado
              ? brl(selecionada.valor_nao_homologado) : "—"],
            ["Situação da declaração", selecionada.situacao_declaracao],
            ["Situação da compensação",
              <Selo cor={COR_SITUACAO_COMPENSACAO[selecionada.situacao_compensacao]}>
                {rotulo(selecionada.situacao_compensacao)}</Selo>],
            ["Despacho decisório", selecionada.numero_despacho
              ?? (selecionada.tem_despacho_decisorio ? "Sim" : "Não informado")],
            ["Data do despacho", data(selecionada.data_despacho)],
            ["Intimação", selecionada.tem_intimacao ? "Sim" : "Não informada"],
            ["Prazo de resposta", data(selecionada.prazo_resposta_intimacao)],
            ["Processo administrativo", selecionada.processo_administrativo],
            ["Origem da informação", selecionada.origem_informacao],
            ["Disponibilidade", rotulo(selecionada.disponibilidade)],
            ["Consultado em", dataHora(selecionada.consultado_em)],
          ]} />

          {selecionada.resultado_analise && (
            <div className="espaco"><Aviso tipo="info">
              <b>Resultado da análise:</b> {selecionada.resultado_analise}
            </Aviso></div>
          )}

          <div className="espaco linha">
            <button className="primario pequeno" onClick={() => consultar(selecionada)}>
              Consultar fonte agora
            </button>
          </div>

          <div className="espaco">
            <h3>Histórico de evolução</h3>
            <ul className="timeline" style={{ marginTop: 12 }}>
              {eventos.map((ev) => (
                <li key={ev.id}>
                  <div className="quando">{dataHora(ev.registrado_em)} · {ev.origem}
                    {ev.criado_por ? ` · ${ev.criado_por}` : ""}</div>
                  <b>{rotulo(ev.tipo)}</b>
                  {ev.situacao_anterior !== ev.situacao_nova && (
                    <div style={{ fontSize: 12 }}>
                      {rotulo(ev.situacao_anterior)} → <b>{rotulo(ev.situacao_nova)}</b>
                    </div>
                  )}
                  {ev.disponibilidade && (
                    <div style={{ fontSize: 11, color: "var(--cinza-500)" }}>
                      disponibilidade: {ev.disponibilidade}
                    </div>
                  )}
                  {ev.mensagem && (
                    <div style={{ fontSize: 12, color: "var(--cinza-500)" }}>{ev.mensagem}</div>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="espaco">
            <h3>Registrar resultado oficial manualmente</h3>
            <p style={{ fontSize: 12, color: "var(--cinza-500)" }}>
              Use quando a consulta automática não estiver autorizada: o resultado lido no
              e-CAC/PER-DCOMP Web é gravado com origem <code>IMPORTACAO_RELATORIO</code> e a data de hoje.
            </p>
            <div className="grade g3" style={{ marginTop: 10 }}>
              <div>
                <label>Situação</label>
                <select value={manual.situacao_compensacao}
                        onChange={(e) => setManual({ ...manual, situacao_compensacao: e.target.value })}>
                  {SITUACOES.map((s) => <option key={s} value={s}>{rotulo(s)}</option>)}
                </select>
              </div>
              <div>
                <label>Nº do despacho decisório</label>
                <input value={manual.numero_despacho}
                       onChange={(e) => setManual({ ...manual, numero_despacho: e.target.value })} />
              </div>
              <div>
                <label>Valor não homologado</label>
                <input value={manual.valor_nao_homologado} placeholder="0,00"
                       onChange={(e) => setManual({ ...manual, valor_nao_homologado: e.target.value })} />
              </div>
            </div>
            <div className="espaco">
              <label>Resultado da análise</label>
              <textarea rows={2} value={manual.resultado_analise}
                        onChange={(e) => setManual({ ...manual, resultado_analise: e.target.value })} />
            </div>
            <div className="espaco">
              <button className="azul" onClick={registrarManual}>Gravar resultado</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
