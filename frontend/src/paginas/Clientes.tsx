import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Acoes, Aviso, Campo, Cartao, Carregando, Modal, Paginacao, Selo, Vazio,
} from "../componentes/ui";
import { Cliente, Pagina, api, baixarArquivo } from "../lib/api";
import { cnpj as fmtCnpj, dataHora } from "../lib/formato";

const CLIENTE_VAZIO = {
  cnpj: "", razao_social: "", nome_fantasia: "", email: "", responsavel: "",
  tributos_trabalhados: "", telefone: "", observacoes: "",
};

export default function Clientes() {
  const [dados, setDados] = useState<Pagina<Cliente> | null>(null);
  const [busca, setBusca] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [responsaveis, setResponsaveis] = useState<string[]>([]);
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [novo, setNovo] = useState({ ...CLIENTE_VAZIO });
  const [criando, setCriando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [recarga, setRecarga] = useState(0);
  const navegar = useNavigate();

  useEffect(() => { api.get<string[]>("/clientes/responsaveis").then(setResponsaveis).catch(() => {}); }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      api.get<Pagina<Cliente>>("/clientes", { busca, responsavel, pagina, tamanho: 25 })
        .then(setDados).catch((e) => setErro(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [busca, responsavel, pagina, recarga]);

  async function criarCliente() {
    setSalvando(true);
    setErro(null);
    try {
      const corpo = Object.fromEntries(
        Object.entries(novo).filter(([, v]) => String(v).trim() !== ""),
      );
      const criado = await api.post<Cliente>("/clientes", corpo);
      setCriando(false);
      setNovo({ ...CLIENTE_VAZIO });
      setMensagem(`Cliente ${criado.razao_social} cadastrado.`);
      setRecarga((n) => n + 1);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao cadastrar cliente.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="grade">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {mensagem && <Aviso tipo="ok">{mensagem}</Aviso>}
    <Cartao
      titulo="Clientes"
      descricao="Clique em um cliente para ver procurações, PER/DCOMP, situação fiscal e histórico"
      semPadding
      acoes={
        <>
          <button className="pequeno" disabled={salvando} onClick={async () => {
            setSalvando(true);
            try {
              const nome = await baixarArquivo("/relatorios/carteira.xlsx", { responsavel });
              setMensagem(`Relatório gerado: ${nome}`);
            } catch (e) {
              setErro(e instanceof Error ? e.message : "Falha ao gerar relatório.");
            } finally { setSalvando(false); }
          }}>Exportar carteira (Excel)</button>
          <button className="pequeno" onClick={() => navegar("/importacao")}>Importar planilha</button>
          <button className="primario pequeno" onClick={() => setCriando(true)}>Novo cliente</button>
        </>
      }
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

    {criando && (
      <Modal titulo="Novo cliente" aoFechar={() => setCriando(false)} largura={620}>
        <div className="grade">
          <div className="grade g2">
            <Campo rotulo="CNPJ" valor={novo.cnpj} obrigatorio placeholder="00.000.000/0000-00"
                   ajuda="Validado pelos dígitos verificadores antes de gravar."
                   aoMudar={(v) => setNovo({ ...novo, cnpj: v })} />
            <Campo rotulo="Razão social" valor={novo.razao_social} obrigatorio
                   aoMudar={(v) => setNovo({ ...novo, razao_social: v })} />
            <Campo rotulo="Nome fantasia" valor={novo.nome_fantasia}
                   aoMudar={(v) => setNovo({ ...novo, nome_fantasia: v })} />
            <Campo rotulo="E-mail" tipo="email" valor={novo.email}
                   aoMudar={(v) => setNovo({ ...novo, email: v })} />
            <Campo rotulo="Responsável" valor={novo.responsavel}
                   aoMudar={(v) => setNovo({ ...novo, responsavel: v })} />
            <Campo rotulo="Telefone" valor={novo.telefone}
                   aoMudar={(v) => setNovo({ ...novo, telefone: v })} />
            <Campo rotulo="Tributos trabalhados" valor={novo.tributos_trabalhados}
                   placeholder="PIS/COFINS, IRPJ…"
                   aoMudar={(v) => setNovo({ ...novo, tributos_trabalhados: v })} />
          </div>
          <Campo rotulo="Observações" tipo="textarea" valor={novo.observacoes}
                 aoMudar={(v) => setNovo({ ...novo, observacoes: v })} />
          <Acoes>
            <button onClick={() => setCriando(false)}>Cancelar</button>
            <button className="primario" onClick={criarCliente}
                    disabled={salvando || !novo.cnpj || !novo.razao_social}>
              {salvando ? <span className="carregando" /> : null} Cadastrar
            </button>
          </Acoes>
        </div>
      </Modal>
    )}
    </div>
  );
}
