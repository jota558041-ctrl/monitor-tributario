import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Aviso, Cartao, Carregando, Selo, Vazio } from "../componentes/ui";
import { api, baixarArquivo } from "../lib/api";
import { brl, data, rotulo } from "../lib/formato";

interface Linha {
  id: string; numero_linha: number; acao: string; selecionada: boolean;
  erros: { campo: string; mensagem: string }[]; avisos: { campo: string; mensagem: string }[];
  dados: Record<string, string | null>; dados_brutos: Record<string, string | null>;
  resultado?: string | null; corrigida: boolean; duplicada_de_linha?: number | null;
}
interface Importacao {
  id: string; arquivo_nome: string; status: string; total_linhas: number;
  mapeamento: Record<string, string>; colunas_detectadas: string[]; colunas_ignoradas: string[];
  resumo: Record<string, unknown>; linhas: Linha[]; criado_em: string;
}
interface Campo { nome: string; label: string; tipo: string; entidade: string; obrigatorio: boolean }

const COR_ACAO: Record<string, string> = {
  CRIAR: "verde", ATUALIZAR: "azul", DUPLICADO: "amarelo", ERRO: "vermelho", IGNORAR: "cinza",
};

export default function Importacao() {
  const [campos, setCampos] = useState<Campo[]>([]);
  const [importacao, setImportacao] = useState<Importacao | null>(null);
  const [historico, setHistorico] = useState<Importacao[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [editando, setEditando] = useState<Linha | null>(null);
  const [correcoes, setCorrecoes] = useState<Record<string, string>>({});
  const navegar = useNavigate();

  useEffect(() => {
    api.get<Campo[]>("/importacoes/campos").then(setCampos).catch(() => {});
    api.get<Importacao[]>("/importacoes").then(setHistorico).catch(() => {});
  }, []);

  async function enviarArquivo(arquivo: File) {
    setEnviando(true); setErro(null); setMensagem(null);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      const resultado = await api.upload<Importacao>("/importacoes", corpo);
      setImportacao(resultado);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha no envio.");
    } finally { setEnviando(false); }
  }

  async function salvarCorrecao() {
    if (!importacao || !editando) return;
    try {
      await api.patch(`/importacoes/${importacao.id}/linhas/${editando.id}`, { correcoes });
      const atualizada = await api.get<Importacao>(`/importacoes/${importacao.id}`);
      setImportacao(atualizada);
      setEditando(null); setCorrecoes({});
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao corrigir.");
    }
  }

  async function alternarSelecao(linha: Linha) {
    if (!importacao) return;
    await api.patch(`/importacoes/${importacao.id}/linhas/${linha.id}`,
      { correcoes: {}, selecionada: !linha.selecionada });
    setImportacao(await api.get<Importacao>(`/importacoes/${importacao.id}`));
  }

  async function confirmar() {
    if (!importacao) return;
    setEnviando(true);
    try {
      const resposta = await api.post<{ resumo: Record<string, number> }>(
        `/importacoes/${importacao.id}/confirmar`);
      setMensagem(
        `Importação concluída: ${resposta.resumo.clientes_criados} cliente(s) criado(s), ` +
        `${resposta.resumo.clientes_atualizados} atualizado(s), ` +
        `${resposta.resumo.compensacoes_criadas} PER/DCOMP e ` +
        `${resposta.resumo.procuracoes_criadas} procuração(ões) registradas.`);
      setImportacao(await api.get<Importacao>(`/importacoes/${importacao.id}`));
      setHistorico(await api.get<Importacao[]>("/importacoes"));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao confirmar.");
    } finally { setEnviando(false); }
  }

  async function baixarModelo() {
    try {
      await baixarArquivo("/importacoes/modelo");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao baixar o modelo.");
    }
  }

  const resumo = (importacao?.resumo ?? {}) as Record<string, number>;

  return (
    <div className="grade">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {mensagem && <Aviso tipo="ok">{mensagem}</Aviso>}

      <Cartao titulo="1. Enviar planilha" descricao="Formatos aceitos: .xlsx, .xlsm e .csv (até 20 MB)"
              acoes={<button className="pequeno" onClick={baixarModelo}>Baixar modelo</button>}>
        <div className="linha">
          <input type="file" accept=".xlsx,.xlsm,.csv" disabled={enviando}
                 onChange={(e) => e.target.files?.[0] && enviarArquivo(e.target.files[0])} />
          {enviando && <span className="carregando" />}
        </div>
        <div className="espaco" style={{ fontSize: 12, color: "var(--cinza-500)", lineHeight: 1.7 }}>
          Campos reconhecidos automaticamente:{" "}
          {campos.map((c) => c.label).join(" · ")}.
          <br />Somente o CNPJ é obrigatório. Várias linhas podem apontar para o mesmo CNPJ
          (uma PER/DCOMP por linha).
        </div>
      </Cartao>

      {importacao && (
        <>
          <Cartao titulo="2. Colunas detectadas"
                  descricao={`Arquivo ${importacao.arquivo_nome} · ${importacao.total_linhas} linha(s)`}>
            <div className="linha">
              {Object.entries(importacao.mapeamento).map(([coluna, campo]) => (
                <Selo key={coluna} cor="azul" titulo={`${coluna} → ${campo}`}>
                  {coluna} → {campo}
                </Selo>
              ))}
            </div>
            {importacao.colunas_ignoradas.length > 0 && (
              <div className="espaco">
                <Aviso tipo="atencao">
                  Colunas não reconhecidas (ignoradas): {importacao.colunas_ignoradas.join(", ")}.
                </Aviso>
              </div>
            )}
          </Cartao>

          <Cartao titulo="3. Validação e correção" semPadding
                  descricao="Linhas com erro ficam bloqueadas até correção; duplicadas não são importadas"
                  acoes={importacao.status !== "CONFIRMADO" ? (
                    <button className="primario pequeno" onClick={confirmar}
                            disabled={enviando || (resumo.selecionadas ?? 0) === 0}>
                      Confirmar importação ({resumo.selecionadas ?? 0})
                    </button>
                  ) : <Selo cor="verde">Confirmada</Selo>}>
            <div className="linha" style={{ padding: "12px 16px", gap: 16 }}>
              <Selo cor="verde">Criar: {resumo.por_acao ? (resumo as any).por_acao.CRIAR ?? 0 : 0}</Selo>
              <Selo cor="azul">Atualizar: {(resumo as any).por_acao?.ATUALIZAR ?? 0}</Selo>
              <Selo cor="amarelo">Duplicadas: {(resumo as any).por_acao?.DUPLICADO ?? 0}</Selo>
              <Selo cor="vermelho">Com erro: {resumo.com_erro ?? 0}</Selo>
              <Selo cor="cinza">Com aviso: {resumo.com_aviso ?? 0}</Selo>
              <span style={{ fontSize: 12, color: "var(--cinza-500)" }}>
                {resumo.clientes_distintos ?? 0} CNPJ distintos · {resumo.perdcomps ?? 0} PER/DCOMP
              </span>
            </div>
            <table>
              <thead>
                <tr><th>#</th><th>CNPJ</th><th>Razão social</th><th>PER/DCOMP</th>
                    <th className="num">Valor</th><th>Validade proc.</th><th>Ação</th>
                    <th>Problemas</th><th /></tr>
              </thead>
              <tbody>
                {importacao.linhas.map((linha) => (
                  <tr key={linha.id} style={!linha.selecionada ? { opacity: .55 } : undefined}>
                    <td>{linha.numero_linha}</td>
                    <td className="mono">{linha.dados.cnpj ?? "—"}</td>
                    <td>{linha.dados.razao_social ?? "—"}</td>
                    <td className="mono" style={{ fontSize: 11 }}>{linha.dados.numero_perdcomp ?? "—"}</td>
                    <td className="num">{linha.dados.valor_compensacao ? brl(linha.dados.valor_compensacao) : "—"}</td>
                    <td>{data(linha.dados.validade_procuracao)}</td>
                    <td><Selo cor={COR_ACAO[linha.acao]}>{rotulo(linha.acao)}</Selo></td>
                    <td style={{ fontSize: 11, maxWidth: 320 }}>
                      {linha.erros.map((e, i) => (
                        <div key={`e${i}`} style={{ color: "var(--vermelho)" }}>● {e.mensagem}</div>
                      ))}
                      {linha.avisos.map((a, i) => (
                        <div key={`a${i}`} style={{ color: "var(--amarelo)" }}>● {a.mensagem}</div>
                      ))}
                      {linha.resultado && (
                        <div style={{ color: "var(--cinza-500)" }}>{linha.resultado}</div>
                      )}
                    </td>
                    <td>
                      {importacao.status !== "CONFIRMADO" && (
                        <div className="linha" style={{ gap: 4 }}>
                          <button className="link pequeno" onClick={() => {
                            setEditando(linha);
                            setCorrecoes(Object.fromEntries(
                              Object.entries(linha.dados).map(([k, v]) => [k, v ?? ""]),
                            ) as Record<string, string>);
                          }}>Corrigir</button>
                          <button className="link pequeno" onClick={() => alternarSelecao(linha)}>
                            {linha.selecionada ? "Ignorar" : "Incluir"}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Cartao>

          {importacao.status === "CONFIRMADO" && (
            <div className="linha">
              <button className="primario" onClick={() => navegar("/clientes")}>Ver clientes</button>
              <button onClick={() => navegar("/monitoramento")}>Executar monitoramento</button>
            </div>
          )}
        </>
      )}

      {editando && (
        <div className="modal-fundo" onClick={() => setEditando(null)}>
          <div className="modal" style={{ width: "min(620px, 100%)" }} onClick={(e) => e.stopPropagation()}>
            <header><h2>Corrigir linha {editando.numero_linha}</h2>
              <button onClick={() => setEditando(null)}>Fechar</button></header>
            <div className="corpo grade">
              {campos.filter((c) => ["cnpj", "razao_social", "email", "responsavel",
                "numero_procuracao", "validade_procuracao", "numero_perdcomp",
                "valor_compensacao", "data_operacao", "tributo"].includes(c.nome)).map((campo) => (
                <div key={campo.nome}>
                  <label>{campo.label}{campo.obrigatorio ? " *" : ""}</label>
                  <input value={correcoes[campo.nome] ?? ""}
                         onChange={(e) => setCorrecoes({ ...correcoes, [campo.nome]: e.target.value })} />
                </div>
              ))}
              <div className="linha">
                <button className="primario" onClick={salvarCorrecao}>Salvar e revalidar</button>
                <button onClick={() => setEditando(null)}>Cancelar</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <Cartao titulo="Importações anteriores" semPadding>
        {historico.length === 0 ? <Vazio>Nenhuma importação registrada.</Vazio> : (
          <table>
            <thead><tr><th>Arquivo</th><th>Status</th><th className="num">Linhas</th>
                        <th>Usuário</th><th>Criada em</th><th>Confirmada em</th></tr></thead>
            <tbody>
              {historico.map((i) => (
                <tr key={i.id} className="clicavel" onClick={() =>
                  api.get<Importacao>(`/importacoes/${i.id}`).then(setImportacao)}>
                  <td>{i.arquivo_nome}</td>
                  <td><Selo cor={i.status === "CONFIRMADO" ? "verde" : i.status === "CANCELADO" ? "cinza" : "azul"}>
                    {rotulo(i.status)}</Selo></td>
                  <td className="num">{i.total_linhas}</td>
                  <td style={{ fontSize: 12 }}>{(i as any).usuario_email ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>{new Date(i.criado_em).toLocaleString("pt-BR")}</td>
                  <td style={{ fontSize: 12 }}>
                    {(i as any).confirmado_em
                      ? new Date((i as any).confirmado_em).toLocaleString("pt-BR") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>
    </div>
  );
}
