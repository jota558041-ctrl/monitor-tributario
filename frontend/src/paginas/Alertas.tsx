import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Aviso, Cartao, Carregando, Modal, Paginacao, Selo, Vazio } from "../componentes/ui";
import { Alerta, Pagina, api } from "../lib/api";
import { COR_CRITICIDADE, dataHora, rotulo } from "../lib/formato";

export default function Alertas() {
  const [dados, setDados] = useState<Pagina<Alerta> | null>(null);
  const [tipos, setTipos] = useState<{ tipo: string; criticidade: string; quantidade: number }[]>([]);
  const [filtros, setFiltros] = useState({ status: "NOVO", criticidade: "", tipo: "" });
  const [pagina, setPagina] = useState(1);
  const [selecionado, setSelecionado] = useState<Alerta | null>(null);
  const [nota, setNota] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const navegar = useNavigate();

  function carregar() {
    api.get<Pagina<Alerta>>("/alertas", { ...filtros, pagina, tamanho: 25 })
      .then(setDados).catch((e) => setErro(e.message));
    api.get<{ tipo: string; criticidade: string; quantidade: number }[]>("/alertas/tipos")
      .then(setTipos).catch(() => {});
  }
  useEffect(carregar, [filtros, pagina]);

  async function agir(status: "RESOLVIDO" | "EM_ANALISE" | "IGNORADO") {
    if (!selecionado) return;
    await api.post(`/alertas/${selecionado.id}/acao`, { status, nota: nota || undefined });
    setSelecionado(null); setNota("");
    carregar();
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  const porTipo = Object.entries(
    tipos.reduce<Record<string, number>>((acc, t) => {
      acc[t.tipo] = (acc[t.tipo] ?? 0) + t.quantidade; return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grade">
      <Cartao titulo="Alertas por tipo" descricao="Inclui alertas já resolvidos (histórico completo)">
        <div className="linha">
          {porTipo.length === 0 ? <span style={{ color: "var(--cinza-500)" }}>Nenhum alerta.</span> :
            porTipo.map(([tipo, qtd]) => (
              <button key={tipo} className="pequeno"
                      onClick={() => { setFiltros({ ...filtros, tipo, status: "" }); setPagina(1); }}>
                {rotulo(tipo)} <b>{qtd}</b>
              </button>
            ))}
        </div>
      </Cartao>

      <Cartao titulo="Ocorrências" semPadding>
        <div className="filtros" style={{ padding: 16, borderBottom: "1px solid var(--cinza-100)" }}>
          <div className="campo">
            <label>Status</label>
            <select value={filtros.status}
                    onChange={(e) => { setFiltros({ ...filtros, status: e.target.value }); setPagina(1); }}>
              <option value="">Todos</option>
              {["NOVO", "EM_ANALISE", "RESOLVIDO", "IGNORADO"].map((s) =>
                <option key={s} value={s}>{rotulo(s)}</option>)}
            </select>
          </div>
          <div className="campo">
            <label>Criticidade</label>
            <select value={filtros.criticidade}
                    onChange={(e) => { setFiltros({ ...filtros, criticidade: e.target.value }); setPagina(1); }}>
              <option value="">Todas</option>
              {["CRITICA", "ALTA", "MEDIA", "BAIXA", "INFO"].map((c) =>
                <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="campo" style={{ minWidth: 220 }}>
            <label>Tipo</label>
            <select value={filtros.tipo}
                    onChange={(e) => { setFiltros({ ...filtros, tipo: e.target.value }); setPagina(1); }}>
              <option value="">Todos</option>
              {porTipo.map(([tipo]) => <option key={tipo} value={tipo}>{rotulo(tipo)}</option>)}
            </select>
          </div>
          <button className="pequeno" onClick={() => { setFiltros({ status: "", criticidade: "", tipo: "" }); setPagina(1); }}>
            Limpar filtros
          </button>
        </div>

        {!dados ? <Carregando /> : dados.itens.length === 0 ? (
          <Vazio>Nenhum alerta com os filtros atuais.</Vazio>
        ) : (
          <>
            <table>
              <thead><tr><th>Criticidade</th><th>Alerta</th><th>Cliente</th><th>Status</th>
                          <th>Gerado em</th><th /></tr></thead>
              <tbody>
                {dados.itens.map((a) => (
                  <tr key={a.id} className="clicavel" onClick={() => setSelecionado(a)}>
                    <td><Selo cor={COR_CRITICIDADE[a.criticidade]}>{a.criticidade}</Selo></td>
                    <td>
                      <b style={{ color: "var(--marinho)" }}>{a.titulo}</b>
                      <div style={{ fontSize: 12, color: "var(--cinza-500)", maxWidth: 560 }}>{a.mensagem}</div>
                    </td>
                    <td style={{ fontSize: 12 }}>{a.cliente_razao_social ?? "—"}
                      <div className="mono" style={{ fontSize: 11, color: "var(--cinza-500)" }}>
                        {a.cliente_cnpj}</div></td>
                    <td><Selo cor={a.status === "RESOLVIDO" ? "verde" : a.status === "IGNORADO" ? "cinza" : "azul"}>
                      {rotulo(a.status)}</Selo></td>
                    <td style={{ fontSize: 12 }}>{dataHora(a.gerado_em)}</td>
                    <td><button className="link pequeno">Abrir</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginacao pagina={dados.pagina} total={dados.total} tamanho={dados.tamanho} aoMudar={setPagina} />
          </>
        )}
      </Cartao>

      {selecionado && (
        <Modal titulo={selecionado.titulo} aoFechar={() => setSelecionado(null)}>
          <div className="linha">
            <Selo cor={COR_CRITICIDADE[selecionado.criticidade]}>{selecionado.criticidade}</Selo>
            <Selo cor="azul">{rotulo(selecionado.tipo)}</Selo>
            <Selo cor="cinza">{rotulo(selecionado.status)}</Selo>
            <span style={{ fontSize: 12, color: "var(--cinza-500)" }}>
              gerado em {dataHora(selecionado.gerado_em)}
            </span>
          </div>

          <div className="espaco"><Aviso tipo="atencao">{selecionado.mensagem}</Aviso></div>

          {selecionado.explicacao && (
            <div className="espaco">
              <h3>Por que este alerta foi gerado</h3>
              <p style={{ fontSize: 13, lineHeight: 1.6 }}>{selecionado.explicacao}</p>
            </div>
          )}

          <div className="espaco">
            <h3>Evidências</h3>
            {selecionado.evidencias.length === 0 ? <Vazio>Sem evidências registradas.</Vazio> : (
              selecionado.evidencias.map((ev, i) => (
                <div key={i} className="evidencia">
                  {Object.entries(ev).map(([chave, valor]) => (
                    <div key={chave} style={{ display: "flex", gap: 8 }}>
                      <b style={{ minWidth: 150, color: "var(--marinho)" }}>{rotulo(chave)}</b>
                      <span className="mono" style={{ wordBreak: "break-word" }}>
                        {typeof valor === "object" ? JSON.stringify(valor) : String(valor)}
                      </span>
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>

          {selecionado.cliente_id && (
            <div className="espaco">
              <button className="pequeno" onClick={() => navegar(`/clientes/${selecionado.cliente_id}`)}>
                Abrir ficha do cliente
              </button>
            </div>
          )}

          {selecionado.status !== "RESOLVIDO" && (
            <div className="espaco">
              <label>Nota de tratamento</label>
              <textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)}
                        placeholder="Ex.: conferido no e-CAC em 10/11, despacho juntado ao processo." />
              <div className="espaco linha">
                <button className="primario" onClick={() => agir("RESOLVIDO")}>Marcar como resolvido</button>
                <button onClick={() => agir("EM_ANALISE")}>Em análise</button>
                <button onClick={() => agir("IGNORADO")}>Ignorar</button>
              </div>
            </div>
          )}
          {selecionado.nota_resolucao && (
            <div className="espaco"><Aviso tipo="ok">
              Tratado por {selecionado.resolvido_por} em {dataHora(selecionado.resolvido_em)}:{" "}
              {selecionado.nota_resolucao}
            </Aviso></div>
          )}
        </Modal>
      )}
    </div>
  );
}
