import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Aviso, Cartao, Carregando, Definicoes, Modal, PontoSemaforo, Selo, Vazio,
} from "../componentes/ui";
import {
  Alerta, Cliente, Comparativo, Compensacao, Pagina, Procuracao, Snapshot, api,
} from "../lib/api";
import {
  COR_CRITICIDADE, COR_DISPONIBILIDADE, COR_SITUACAO_COMPENSACAO, COR_SITUACAO_FISCAL,
  brl, cnpj as fmtCnpj, data, dataHora, rotulo,
} from "../lib/formato";

interface ResumoIa {
  metodo: string; resumo: string; topicos: string[]; limites: string[]; gerado_em: string;
}
interface Historico {
  id: string; campo: string; valor_anterior?: string | null; valor_novo?: string | null;
  origem: string; usuario_email?: string | null; created_at: string;
}

export default function ClienteDetalhe() {
  const { id = "" } = useParams();
  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [procuracoes, setProcuracoes] = useState<Procuracao[]>([]);
  const [compensacoes, setCompensacoes] = useState<Compensacao[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [comparativos, setComparativos] = useState<Comparativo[]>([]);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [historico, setHistorico] = useState<Historico[]>([]);
  const [ia, setIa] = useState<ResumoIa | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [verPendencias, setVerPendencias] = useState<Snapshot | null>(null);

  async function carregar() {
    try {
      const [c, pr, co, sn, cp, al, hi, resumoIa] = await Promise.all([
        api.get<Cliente>(`/clientes/${id}`),
        api.get<Pagina<Procuracao>>("/procuracoes", { busca: "", tamanho: 100 }),
        api.get<Pagina<Compensacao>>("/compensacoes", { cliente_id: id, tamanho: 100 }),
        api.get<Snapshot[]>(`/situacao-fiscal/${id}/snapshots`, { limite: 30 }),
        api.get<Comparativo[]>(`/situacao-fiscal/${id}/comparativos`, { limite: 10 }),
        api.get<Pagina<Alerta>>("/alertas", { cliente_id: id, tamanho: 50 }),
        api.get<Historico[]>(`/clientes/${id}/historico`),
        api.get<ResumoIa>(`/ia/resumo/${id}`),
      ]);
      setCliente(c);
      setProcuracoes(pr.itens.filter((p) => p.cliente_id === id));
      setCompensacoes(co.itens);
      setSnapshots(sn);
      setComparativos(cp);
      setAlertas(al.itens);
      setHistorico(hi);
      setIa(resumoIa);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao carregar cliente.");
    }
  }

  useEffect(() => { carregar(); }, [id]);

  async function consultarTudo() {
    setOcupado(true);
    try {
      await api.post("/monitoramento/executar", { tipo: "COMPLETO", clientes_ids: [id] });
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha na consulta.");
    } finally { setOcupado(false); }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!cliente) return <Carregando />;

  const ultimo = snapshots[0];

  return (
    <div className="grade">
      <Cartao
        titulo={cliente.razao_social}
        descricao={`${cliente.cnpj_formatado ?? fmtCnpj(cliente.cnpj)} · ${cliente.nome_fantasia ?? "sem nome fantasia"}`}
        acoes={<button className="primario pequeno" onClick={consultarTudo} disabled={ocupado}>
          {ocupado ? <span className="carregando" /> : null} Consultar agora
        </button>}
      >
        <Definicoes itens={[
          ["Responsável", cliente.responsavel ?? "—"],
          ["E-mail", cliente.email ?? "—"],
          ["Tributos trabalhados", cliente.tributos_trabalhados ?? "—"],
          ["Última consulta de procuração", dataHora(cliente.ultima_consulta_procuracao)],
          ["Última consulta PER/DCOMP", dataHora(cliente.ultima_consulta_compensacao)],
          ["Última consulta fiscal", dataHora(cliente.ultima_consulta_fiscal)],
          ["Situação fiscal atual", ultimo
            ? <Selo cor={COR_SITUACAO_FISCAL[ultimo.situacao_geral]}>{rotulo(ultimo.situacao_geral)}</Selo>
            : <Selo cor="cinza">Nunca consultado</Selo>],
          ["Total de débitos", ultimo ? brl(ultimo.total_debitos) : "—"],
        ]} />
      </Cartao>

      {ia && (
        <Cartao titulo="Resumo interpretado" descricao={`Método: ${ia.metodo} · gerado em ${dataHora(ia.gerado_em)}`}>
          <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7, fontSize: 13 }}>
            {ia.topicos.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
          <div className="espaco">
            <Aviso tipo="info"><b>Limites da interpretação:</b> {ia.limites.join(" ")}</Aviso>
          </div>
        </Cartao>
      )}

      <Cartao titulo="Procurações eletrônicas" semPadding>
        {procuracoes.length === 0 ? <Vazio>Nenhuma procuração cadastrada.</Vazio> : (
          <table>
            <thead>
              <tr><th>Número</th><th>Validade</th><th>Situação (sistema)</th><th>Declarada</th>
                  <th>Validada por fonte</th><th>Disponibilidade</th><th>Última consulta</th></tr>
            </thead>
            <tbody>
              {procuracoes.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.numero ?? "—"}</td>
                  <td>{data(p.data_fim)}{p.dias_para_vencer !== null && p.dias_para_vencer !== undefined && (
                    <span style={{ fontSize: 11, color: "var(--cinza-500)" }}> ({p.dias_para_vencer} d)</span>)}</td>
                  <td><PontoSemaforo valor={p.semaforo ?? "CINZA"} /> {rotulo(p.situacao)}</td>
                  <td style={{ fontSize: 12, color: "var(--cinza-500)" }}>{rotulo(p.situacao_declarada)}</td>
                  <td>{p.validada_por_fonte ? <Selo cor="verde">Sim</Selo> : <Selo cor="cinza">Não</Selo>}</td>
                  <td><Selo cor={COR_DISPONIBILIDADE[p.disponibilidade]}>{rotulo(p.disponibilidade)}</Selo></td>
                  <td style={{ fontSize: 12 }}>{dataHora(p.consultado_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      <Cartao titulo="Compensações (PER/DCOMP)" semPadding>
        {compensacoes.length === 0 ? <Vazio>Nenhuma PER/DCOMP cadastrada.</Vazio> : (
          <table>
            <thead>
              <tr><th>Número</th><th>Tributo</th><th>PA</th><th className="num">Crédito</th>
                  <th className="num">Não homologado</th><th>Situação</th><th>Despacho</th>
                  <th>Intimação</th><th>Consulta</th></tr>
            </thead>
            <tbody>
              {compensacoes.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.numero_perdcomp}</td>
                  <td>{c.tributo ?? "—"}</td>
                  <td>{c.periodo_apuracao ?? "—"}</td>
                  <td className="num">{brl(c.valor_credito)}</td>
                  <td className="num">{c.valor_nao_homologado ? brl(c.valor_nao_homologado) : "—"}</td>
                  <td><Selo cor={COR_SITUACAO_COMPENSACAO[c.situacao_compensacao]}>
                    {rotulo(c.situacao_compensacao)}</Selo></td>
                  <td>{c.tem_despacho_decisorio ? (c.numero_despacho ?? "Sim") : "—"}</td>
                  <td>{c.tem_intimacao ? <Selo cor="vermelho">Sim</Selo> : "—"}</td>
                  <td style={{ fontSize: 12 }}>
                    <Selo cor={COR_DISPONIBILIDADE[c.disponibilidade]}>{rotulo(c.disponibilidade)}</Selo>
                    <div style={{ color: "var(--cinza-500)" }}>{dataHora(c.consultado_em)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      <div className="grade g2">
        <Cartao titulo="Histórico de consultas fiscais" semPadding>
          {snapshots.length === 0 ? <Vazio>Nenhuma consulta registrada.</Vazio> : (
            <table>
              <thead>
                <tr><th>Consulta</th><th>Situação</th><th className="num">Total</th>
                    <th className="num">Pendências</th><th>Origem</th><th /></tr>
              </thead>
              <tbody>
                {snapshots.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontSize: 12 }}>{dataHora(s.consultado_em)}</td>
                    <td><Selo cor={COR_SITUACAO_FISCAL[s.situacao_geral]}>{rotulo(s.situacao_geral)}</Selo></td>
                    <td className="num">{brl(s.total_debitos)}</td>
                    <td className="num">{s.qtd_pendencias}</td>
                    <td style={{ fontSize: 11 }}>{s.origem}</td>
                    <td><button className="link pequeno" onClick={() => setVerPendencias(s)}>Detalhar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>

        <Cartao titulo="Comparativos entre consultas" semPadding>
          {comparativos.length === 0 ? (
            <Vazio>São necessárias duas consultas bem-sucedidas para comparar.</Vazio>
          ) : (
            <div style={{ padding: 16, display: "grid", gap: 12 }}>
              {comparativos.map((c) => {
                const dif = Number(c.diferenca);
                return (
                  <div key={c.id} className="evidencia">
                    <div className="linha" style={{ justifyContent: "space-between" }}>
                      <b>{brl(c.total_anterior)} → {brl(c.total_atual)}</b>
                      <Selo cor={dif > 0 ? "vermelho" : dif < 0 ? "verde" : "cinza"}>
                        {dif > 0 ? "+" : ""}{brl(c.diferenca)}
                      </Selo>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12 }}>
                      {c.novos.length} novo(s) · {c.baixados.length} baixado(s) ·{" "}
                      {c.permanecem.length} remanescente(s) · {c.alterados.length} alterado(s)
                      <div style={{ color: "var(--cinza-500)", marginTop: 4 }}>{dataHora(c.created_at)}</div>
                    </div>
                    {c.ressalva && (
                      <div style={{ marginTop: 8, fontSize: 11, color: "var(--cinza-500)", lineHeight: 1.5 }}>
                        {c.ressalva}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Cartao>
      </div>

      <div className="grade g2">
        <Cartao titulo="Alertas do cliente" semPadding>
          {alertas.length === 0 ? <Vazio>Nenhum alerta.</Vazio> : (
            <table>
              <thead><tr><th>Alerta</th><th>Criticidade</th><th>Status</th><th>Gerado em</th></tr></thead>
              <tbody>
                {alertas.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <b>{a.titulo}</b>
                      <div style={{ fontSize: 12, color: "var(--cinza-500)" }}>{a.mensagem}</div>
                    </td>
                    <td><Selo cor={COR_CRITICIDADE[a.criticidade]}>{a.criticidade}</Selo></td>
                    <td><Selo cor={a.status === "RESOLVIDO" ? "verde" : "azul"}>{rotulo(a.status)}</Selo></td>
                    <td style={{ fontSize: 12 }}>{dataHora(a.gerado_em)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>

        <Cartao titulo="Histórico de alterações cadastrais" semPadding>
          {historico.length === 0 ? <Vazio>Sem alterações registradas.</Vazio> : (
            <table>
              <thead><tr><th>Campo</th><th>De</th><th>Para</th><th>Origem</th><th>Quando</th></tr></thead>
              <tbody>
                {historico.slice(0, 40).map((h) => (
                  <tr key={h.id}>
                    <td>{rotulo(h.campo)}</td>
                    <td style={{ fontSize: 12 }}>{h.valor_anterior ?? "—"}</td>
                    <td style={{ fontSize: 12 }}>{h.valor_novo ?? "—"}</td>
                    <td style={{ fontSize: 11 }}>{h.origem}</td>
                    <td style={{ fontSize: 12 }}>{dataHora(h.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>
      </div>

      {verPendencias && (
        <Modal titulo={`Pendências — consulta de ${dataHora(verPendencias.consultado_em)}`}
               aoFechar={() => setVerPendencias(null)}>
          <Definicoes itens={[
            ["Origem", verPendencias.origem],
            ["Disponibilidade", rotulo(verPendencias.disponibilidade)],
            ["Total exigível", brl(verPendencias.total_debitos)],
            ["Previdenciário", brl(verPendencias.total_previdenciario)],
            ["Federal", brl(verPendencias.total_federal)],
            ["Em cobrança", brl(verPendencias.total_em_cobranca)],
            ["Suspenso", brl(verPendencias.total_suspenso)],
            ["Parcelado", brl(verPendencias.total_parcelado)],
          ]} />
          <div className="espaco">
            {verPendencias.pendencias.length === 0 ? (
              <Aviso tipo={verPendencias.disponibilidade === "OK" ? "ok" : "atencao"}>
                {verPendencias.disponibilidade === "OK"
                  ? "Nenhuma pendência retornada nesta consulta."
                  : `Consulta sem resultado (${verPendencias.disponibilidade}). ${verPendencias.mensagem ?? ""}`}
              </Aviso>
            ) : (
              <table>
                <thead><tr><th>Categoria</th><th>Código</th><th>Descrição</th><th>Período</th>
                            <th className="num">Valor</th><th>Situação</th></tr></thead>
                <tbody>
                  {verPendencias.pendencias.map((p, i) => (
                    <tr key={i}>
                      <td style={{ fontSize: 11 }}>{rotulo(p.categoria)}</td>
                      <td className="mono">{p.codigo ?? "—"}</td>
                      <td style={{ fontSize: 12 }}>{p.descricao}</td>
                      <td>{p.periodo ?? "—"}</td>
                      <td className="num">{brl(p.valor)}</td>
                      <td style={{ fontSize: 11 }}>{p.situacao ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
