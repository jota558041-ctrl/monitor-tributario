import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Aviso, Cartao, Carregando, Paginacao, Selo, Vazio } from "../componentes/ui";
import { Cliente, Pagina, api } from "../lib/api";
import { cnpj as fmtCnpj, dataHora } from "../lib/formato";

export default function Clientes() {
  const [dados, setDados] = useState<Pagina<Cliente> | null>(null);
  const [busca, setBusca] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [responsaveis, setResponsaveis] = useState<string[]>([]);
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState<string | null>(null);
  const navegar = useNavigate();

  useEffect(() => { api.get<string[]>("/clientes/responsaveis").then(setResponsaveis).catch(() => {}); }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      api.get<Pagina<Cliente>>("/clientes", { busca, responsavel, pagina, tamanho: 25 })
        .then(setDados).catch((e) => setErro(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [busca, responsavel, pagina]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  return (
    <Cartao
      titulo="Clientes"
      descricao="Clique em um cliente para ver procurações, PER/DCOMP, situação fiscal e histórico"
      semPadding
      acoes={<button className="primario pequeno" onClick={() => navegar("/importacao")}>Importar planilha</button>}
    >
      <div style={{ padding: 16, borderBottom: "1px solid var(--cinza-100)" }} className="filtros">
        <div className="campo" style={{ flex: 1, minWidth: 260 }}>
          <label>Buscar</label>
          <input placeholder="CNPJ, razão social ou nome fantasia" value={busca}
                 onChange={(e) => { setBusca(e.target.value); setPagina(1); }} />
        </div>
        <div className="campo">
          <label>Responsável</label>
          <select value={responsavel} onChange={(e) => { setResponsavel(e.target.value); setPagina(1); }}>
            <option value="">Todos</option>
            {responsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      </div>

      {!dados ? <Carregando /> : dados.itens.length === 0 ? (
        <Vazio>Nenhum cliente encontrado. Importe uma planilha para começar.</Vazio>
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th>Cliente</th><th>CNPJ</th><th>Responsável</th><th>Tributos</th>
                <th>Última consulta fiscal</th><th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {dados.itens.map((c) => (
                <tr key={c.id} className="clicavel" onClick={() => navegar(`/clientes/${c.id}`)}>
                  <td>
                    <b style={{ color: "var(--marinho)" }}>{c.razao_social}</b>
                    {c.nome_fantasia && (
                      <div style={{ fontSize: 12, color: "var(--cinza-500)" }}>{c.nome_fantasia}</div>
                    )}
                  </td>
                  <td className="mono">{c.cnpj_formatado ?? fmtCnpj(c.cnpj)}</td>
                  <td>{c.responsavel ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>{c.tributos_trabalhados ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>
                    {c.ultima_consulta_fiscal ? dataHora(c.ultima_consulta_fiscal)
                      : <Selo cor="cinza">Nunca consultado</Selo>}
                  </td>
                  <td>{c.ativo ? <Selo cor="verde">Ativo</Selo> : <Selo cor="cinza">Inativo</Selo>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao pagina={dados.pagina} total={dados.total} tamanho={dados.tamanho} aoMudar={setPagina} />
        </>
      )}
    </Cartao>
  );
}
