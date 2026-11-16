import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Aviso, Cartao, Carregando, Kpi, Modal, Selo, Vazio } from "../componentes/ui";
import { Comparativo, Snapshot, api } from "../lib/api";
import { COR_SITUACAO_FISCAL, brl, dataHora, rotulo } from "../lib/formato";

interface LinhaVisao {
  cliente_id: string; cnpj: string; razao_social: string; responsavel?: string | null;
  situacao_geral: string; disponibilidade: string; total_debitos?: string | null;
  qtd_pendencias?: number | null; consultado_em?: string | null; origem?: string | null;
  total_anterior?: string | null; variacao?: string | null;
}

export default function SituacaoFiscal() {
  const [visao, setVisao] = useState<LinhaVisao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<{ linha: LinhaVisao; snapshots: Snapshot[];
    comparativos: Comparativo[] } | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const navegar = useNavigate();

  function carregar() {
    api.get<LinhaVisao[]>("/situacao-fiscal/visao-geral").then(setVisao).catch((e) => setErro(e.message));
  }
  useEffect(carregar, []);

  async function abrir(linha: LinhaVisao) {
    const [snapshots, comparativos] = await Promise.all([
      api.get<Snapshot[]>(`/situacao-fiscal/${linha.cliente_id}/snapshots`, { limite: 20 }),
      api.get<Comparativo[]>(`/situacao-fiscal/${linha.cliente_id}/comparativos`, { limite: 10 }),
    ]);
    setDetalhe({ linha, snapshots, comparativos });
  }

  async function consultar(linha: LinhaVisao) {
    setOcupado(linha.cliente_id);
    try {
      await api.post(`/situacao-fiscal/${linha.cliente_id}/consultar`);
      carregar();
      await abrir(linha);
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha na consulta."); }
    finally { setOcupado(null); }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!visao) return <Carregando />;

  const comPendencias = visao.filter((v) => v.situacao_geral === "COM_PENDENCIAS");
  const regulares = visao.filter((v) => v.situacao_geral === "REGULAR");
  const indisponiveis = visao.filter((v) => v.disponibilidade !== "OK" && v.consultado_em);
  const nuncaConsultados = visao.filter((v) => !v.consultado_em);
  const total = comPendencias.reduce((soma, v) => soma + Number(v.total_debitos ?? 0), 0);

  return (
    <div className="grade">
      <Aviso tipo="info">
        Cada consulta gera um <b>snapshot imutável</b>. A comparação mostra novos débitos, baixados,
        remanescentes e alterados — <b>sem presumir</b> que a variação decorra das compensações.
      </Aviso>

      <div className="grade g4">
        <Kpi rotulo="Clientes com débitos" valor={comPendencias.length} cor="vermelho" nota={brl(total)} />
        <Kpi rotulo="Sem pendências identificadas" valor={regulares.length} cor="verde" />
        <Kpi rotulo="Consulta indisponível" valor={indisponiveis.length} cor="amarelo"
             nota="Indisponibilidade ≠ regularidade" />
        <Kpi rotulo="Nunca consultados" valor={nuncaConsultados.length} cor="cinza" />
      </div>

      <Cartao titulo="Situação fiscal por cliente" semPadding>
        <table>
          <thead>
            <tr><th>Cliente</th><th>Responsável</th><th>Situação</th><th className="num">Total atual</th>
                <th className="num">Consulta anterior</th><th className="num">Variação</th>
                <th className="num">Pendências</th><th>Última consulta</th><th /></tr>
          </thead>
          <tbody>
            {visao.map((v) => {
              const variacao = v.variacao ? Number(v.variacao) : null;
              return (
                <tr key={v.cliente_id}>
                  <td className="clicavel" onClick={() => navegar(`/clientes/${v.cliente_id}`)}>
                    <b style={{ color: "var(--marinho)" }}>{v.razao_social}</b>
                    <div className="mono" style={{ fontSize: 11, color: "var(--cinza-500)" }}>{v.cnpj}</div>
                  </td>
                  <td>{v.responsavel ?? "—"}</td>
                  <td>
                    <Selo cor={COR_SITUACAO_FISCAL[v.situacao_geral] ?? "cinza"}>
                      {rotulo(v.situacao_geral)}
                    </Selo>
                    {v.disponibilidade !== "OK" && v.consultado_em && (
                      <div style={{ fontSize: 11, color: "var(--cinza-500)" }}>{rotulo(v.disponibilidade)}</div>
                    )}
                  </td>
                  <td className="num">{v.total_debitos ? brl(v.total_debitos) : "—"}</td>
                  <td className="num">{v.total_anterior ? brl(v.total_anterior) : "—"}</td>
                  <td className="num">
                    {variacao === null ? "—" : (
                      <Selo cor={variacao > 0 ? "vermelho" : variacao < 0 ? "verde" : "cinza"}>
                        {variacao > 0 ? "+" : ""}{brl(v.variacao)}
                      </Selo>
                    )}
                  </td>
                  <td className="num">{v.qtd_pendencias ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>
                    {v.consultado_em ? dataHora(v.consultado_em) : <Selo cor="cinza">Nunca</Selo>}
                  </td>
                  <td>
                    <div className="linha" style={{ gap: 4 }}>
                      <button className="link pequeno" onClick={() => abrir(v)}>Histórico</button>
                      <button className="link pequeno" disabled={ocupado === v.cliente_id}
                              onClick={() => consultar(v)}>Consultar</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Cartao>

      {detalhe && (
        <Modal titulo={`Situação fiscal — ${detalhe.linha.razao_social}`} aoFechar={() => setDetalhe(null)}>
          <h3>Consultas registradas</h3>
          <table style={{ marginTop: 10 }}>
            <thead><tr><th>Quando</th><th>Origem</th><th>Disponibilidade</th><th>Situação</th>
                        <th className="num">Total</th><th className="num">Pendências</th></tr></thead>
            <tbody>
              {detalhe.snapshots.map((s) => (
                <tr key={s.id}>
                  <td style={{ fontSize: 12 }}>{dataHora(s.consultado_em)}</td>
                  <td style={{ fontSize: 11 }}>{s.origem}</td>
                  <td><Selo cor={s.disponibilidade === "OK" ? "verde" : "amarelo"}>
                    {rotulo(s.disponibilidade)}</Selo></td>
                  <td>{rotulo(s.situacao_geral)}</td>
                  <td className="num">{brl(s.total_debitos)}</td>
                  <td className="num">{s.qtd_pendencias}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="espaco">
            <h3>Comparativos</h3>
            {detalhe.comparativos.length === 0 ? (
              <Vazio>Sem comparativos (são necessárias duas consultas bem-sucedidas).</Vazio>
            ) : detalhe.comparativos.map((c) => (
              <div key={c.id} className="evidencia" style={{ marginTop: 10 }}>
                <div className="linha" style={{ justifyContent: "space-between" }}>
                  <b>{brl(c.total_anterior)} → {brl(c.total_atual)}</b>
                  <Selo cor={Number(c.diferenca) > 0 ? "vermelho" : Number(c.diferenca) < 0 ? "verde" : "cinza"}>
                    {Number(c.diferenca) > 0 ? "+" : ""}{brl(c.diferenca)}
                  </Selo>
                </div>
                {[["Novos", c.novos, "vermelho"], ["Baixados", c.baixados, "verde"],
                  ["Remanescentes", c.permanecem, "amarelo"], ["Alterados", c.alterados, "azul"]]
                  .map(([titulo, itens, cor]) => {
                    const lista = itens as Record<string, string>[];
                    if (lista.length === 0) return null;
                    return (
                      <div key={titulo as string} style={{ marginTop: 8 }}>
                        <Selo cor={cor as string}>{titulo as string}: {lista.length}</Selo>
                        <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12 }}>
                          {lista.map((p, i) => (
                            <li key={i}>
                              {rotulo(p.categoria)} · {p.codigo ?? "s/código"} · {p.periodo ?? "s/período"} ·{" "}
                              {brl(p.valor)}
                              {p.valor_anterior ? ` (antes ${brl(p.valor_anterior)})` : ""}
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                <div style={{ marginTop: 10, fontSize: 11, color: "var(--cinza-500)", lineHeight: 1.5 }}>
                  {c.ressalva}
                </div>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
