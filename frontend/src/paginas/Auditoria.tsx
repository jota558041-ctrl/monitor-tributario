import { useEffect, useState } from "react";
import { Aviso, Cartao, Carregando, Paginacao, Selo, Vazio } from "../componentes/ui";
import { api } from "../lib/api";
import { dataHora, rotulo } from "../lib/formato";

interface Registro {
  id: string; acao: string; entidade?: string | null; entidade_id?: string | null;
  usuario_email?: string | null; descricao?: string | null; ip?: string | null;
  detalhe?: Record<string, unknown> | null; created_at: string;
}
interface Resposta { total: number; pagina: number; tamanho: number; itens: Registro[] }

const ACOES = ["LOGIN", "LOGIN_FALHA", "LEITURA", "CRIACAO", "ALTERACAO", "EXCLUSAO",
  "IMPORTACAO_CARREGADA", "IMPORTACAO_CORRECAO", "IMPORTACAO_CONFIRMADA",
  "CONSULTA_FONTE", "RESULTADO_MANUAL", "MONITORAMENTO", "SIMULACAO", "ALERTA_ACAO",
  "IA_RESUMO", "TROCA_SENHA"];

export default function Auditoria() {
  const [dados, setDados] = useState<Resposta | null>(null);
  const [filtros, setFiltros] = useState({ acao: "", usuario_email: "", entidade: "" });
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api.get<Resposta>("/auditoria", { ...filtros, pagina, tamanho: 50 })
      .then(setDados).catch((e) => setErro(e.message));
  }, [filtros, pagina]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  return (
    <div className="grade">
      <Aviso tipo="info">
        Registro de acessos e alterações (LGPD). Inclui leitura de ficha de cliente, consultas às
        fontes, importações, simulações e tratamento de alertas.
      </Aviso>

      <Cartao titulo="Registros" semPadding>
        <div className="filtros" style={{ padding: 16, borderBottom: "1px solid var(--cinza-100)" }}>
          <div className="campo">
            <label>Ação</label>
            <select value={filtros.acao}
                    onChange={(e) => { setFiltros({ ...filtros, acao: e.target.value }); setPagina(1); }}>
              <option value="">Todas</option>
              {ACOES.map((a) => <option key={a} value={a}>{rotulo(a)}</option>)}
            </select>
          </div>
          <div className="campo">
            <label>Usuário</label>
            <input value={filtros.usuario_email} placeholder="e-mail"
                   onChange={(e) => { setFiltros({ ...filtros, usuario_email: e.target.value }); setPagina(1); }} />
          </div>
          <div className="campo">
            <label>Entidade</label>
            <input value={filtros.entidade} placeholder="CLIENTE, COMPENSACAO…"
                   onChange={(e) => { setFiltros({ ...filtros, entidade: e.target.value.toUpperCase() }); setPagina(1); }} />
          </div>
        </div>

        {!dados ? <Carregando /> : dados.itens.length === 0 ? <Vazio>Nenhum registro.</Vazio> : (
          <>
            <table>
              <thead><tr><th>Quando</th><th>Ação</th><th>Usuário</th><th>Entidade</th>
                          <th>Detalhe</th><th>IP</th></tr></thead>
              <tbody>
                {dados.itens.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontSize: 12 }}>{dataHora(r.created_at)}</td>
                    <td><Selo cor={r.acao.includes("FALHA") ? "vermelho"
                      : r.acao === "LEITURA" ? "cinza" : "azul"}>{rotulo(r.acao)}</Selo></td>
                    <td style={{ fontSize: 12 }}>{r.usuario_email ?? "—"}</td>
                    <td style={{ fontSize: 12 }}>{r.entidade ?? "—"}
                      {r.entidade_id && (
                        <div className="mono" style={{ fontSize: 10, color: "var(--cinza-500)" }}>
                          {r.entidade_id.slice(0, 12)}…
                        </div>
                      )}</td>
                    <td style={{ fontSize: 11, maxWidth: 420, wordBreak: "break-word" }}>
                      {r.descricao ?? (r.detalhe ? JSON.stringify(r.detalhe).slice(0, 180) : "—")}
                    </td>
                    <td className="mono" style={{ fontSize: 11 }}>{r.ip ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginacao pagina={dados.pagina} total={dados.total} tamanho={dados.tamanho} aoMudar={setPagina} />
          </>
        )}
      </Cartao>
    </div>
  );
}
