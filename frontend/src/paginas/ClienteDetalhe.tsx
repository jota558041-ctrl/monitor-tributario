import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Acoes, Aviso, Campo, Cartao, Carregando, Definicoes, Modal, PontoSemaforo, Selo, Vazio,
} from "../componentes/ui";
import {
  Alerta, Cliente, Comparativo, Compensacao, Pagina, Procuracao, Snapshot, api, obterUsuario,
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
  const [editandoCliente, setEditandoCliente] = useState<Record<string, string> | null>(null);
  const [formProc, setFormProc] = useState<Record<string, string> | null>(null);
  const [formComp, setFormComp] = useState<Record<string, string> | null>(null);
  const perfil = obterUsuario()?.perfil;

  function abrirEdicaoCliente() {
    if (!cliente) return;
    setEditandoCliente({
      razao_social: cliente.razao_social ?? "", nome_fantasia: cliente.nome_fantasia ?? "",
      email: cliente.email ?? "", responsavel: cliente.responsavel ?? "",
      telefone: cliente.telefone ?? "", tributos_trabalhados: cliente.tributos_trabalhados ?? "",
      observacoes: cliente.observacoes ?? "",
    });
  }

  async function salvarCliente() {
    if (!editandoCliente) return;
    setOcupado(true);
    try {
      await api.patch(`/clientes/${id}`, editandoCliente);
      setEditandoCliente(null);
      await carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao salvar."); }
    finally { setOcupado(false); }
  }

  async function salvarProcuracao() {
    if (!formProc) return;
    setOcupado(true);
    try {
      const corpo: Record<string, unknown> = Object.fromEntries(
        Object.entries(formProc).filter(([k, v]) => k !== "id" && String(v).trim() !== ""),
      );
      if (formProc.id) {
        await api.patch(`/procuracoes/${formProc.id}`, corpo);
      } else {
        await api.post("/procuracoes", { ...corpo, cliente_id: id });
      }
      setFormProc(null);
      await carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao salvar procuração."); }
    finally { setOcupado(false); }
  }

  async function salvarCompensacao() {
    if (!formComp) return;
    setOcupado(true);
    try {
      const corpo: Record<string, unknown> = Object.fromEntries(
        Object.entries(formComp).filter(([k, v]) => k !== "id" && String(v).trim() !== ""),
      );
      if (formComp.id) {
        delete corpo.numero_perdcomp;
        await api.patch(`/compensacoes/${formComp.id}`, corpo);
      } else {
        await api.post("/compensacoes", { ...corpo, cliente_id: id });
      }
      setFormComp(null);
      await carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao salvar PER/DCOMP."); }
    finally { setOcupado(false); }
  }

  async function excluir(tipo: "procuracoes" | "compensacoes", registroId: string, rotulo: string) {
    if (!window.confirm(`Excluir ${rotulo}? O histórico vinculado também será removido.`)) return;
    setOcupado(true);
    try {
      await api.delete(`/${tipo}/${registroId}`);
      await carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao excluir."); }
    finally { setOcupado(false); }
  }

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
        acoes={
          <>
            <button className="pequeno" onClick={abrirEdicaoCliente}>Editar cliente</button>
            <button className="primario pequeno" onClick={consultarTudo} disabled={ocupado}>
              {ocupado ? <span className="carregando" /> : null} Consultar agora
            </button>
          </>
        }
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

      <Cartao titulo="Procurações eletrônicas" semPadding
              acoes={<button className="pequeno" onClick={() => setFormProc({
                numero: "", procurador_doc: "", data_inicio: "", data_fim: "", observacoes: "",
              })}>Nova procuração</button>}>
        {procuracoes.length === 0 ? <Vazio>Nenhuma procuração cadastrada.</Vazio> : (
          <table>
            <thead>
              <tr><th>Número</th><th>Validade</th><th>Situação (sistema)</th><th>Declarada</th>
                  <th>Validada por fonte</th><th>Disponibilidade</th><th>Última consulta</th>
                  <th /></tr>
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
                  <td>
                    <div className="linha" style={{ gap: 4 }}>
                      <button className="link pequeno" onClick={() => setFormProc({
                        id: p.id, numero: p.numero ?? "", procurador_doc: p.procurador_doc ?? "",
                        data_inicio: p.data_inicio ?? "", data_fim: p.data_fim ?? "",
                        observacoes: p.observacoes ?? "",
                      })}>Editar</button>
                      {perfil === "ADMIN" && (
                        <button className="link pequeno" style={{ color: "var(--vermelho)" }}
                                onClick={() => excluir("procuracoes", p.id,
                                  `a procuração ${p.numero ?? ""}`)}>Excluir</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      <Cartao titulo="Compensações (PER/DCOMP)" semPadding
              acoes={<button className="pequeno" onClick={() => setFormComp({
                numero_perdcomp: "", tributo: "", periodo_apuracao: "", data_transmissao: "",
                valor_debito: "", valor_credito: "", situacao_declaracao: "", observacoes: "",
              })}>Nova PER/DCOMP</button>}>
        {compensacoes.length === 0 ? <Vazio>Nenhuma PER/DCOMP cadastrada.</Vazio> : (
          <table>
            <thead>
              <tr><th>Número</th><th>Tributo</th><th>PA</th><th className="num">Crédito</th>
                  <th className="num">Não homologado</th><th>Situação</th><th>Despacho</th>
                  <th>Intimação</th><th>Consulta</th><th /></tr>
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
                  <td>
                    <div className="linha" style={{ gap: 4 }}>
                      <button className="link pequeno" onClick={() => setFormComp({
                        id: c.id, numero_perdcomp: c.numero_perdcomp, tributo: c.tributo ?? "",
                        periodo_apuracao: c.periodo_apuracao ?? "",
                        data_transmissao: c.data_transmissao ?? "",
                        valor_debito: c.valor_debito ?? "", valor_credito: c.valor_credito ?? "",
                        situacao_declaracao: c.situacao_declaracao ?? "",
                        observacoes: c.observacoes ?? "",
                      })}>Editar</button>
                      {perfil === "ADMIN" && (
                        <button className="link pequeno" style={{ color: "var(--vermelho)" }}
                                onClick={() => excluir("compensacoes", c.id,
                                  `a PER/DCOMP ${c.numero_perdcomp}`)}>Excluir</button>
                      )}
                    </div>
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
      {editandoCliente && (
        <Modal titulo="Editar cliente" aoFechar={() => setEditandoCliente(null)} largura={620}>
          <div className="grade">
            <Aviso tipo="info">
              O CNPJ não é editável: para corrigi-lo, cadastre o cliente correto. Toda alteração
              fica registrada no histórico, campo a campo.
            </Aviso>
            <div className="grade g2">
              <Campo rotulo="Razão social" valor={editandoCliente.razao_social} obrigatorio
                     aoMudar={(v) => setEditandoCliente({ ...editandoCliente, razao_social: v })} />
              <Campo rotulo="Nome fantasia" valor={editandoCliente.nome_fantasia}
                     aoMudar={(v) => setEditandoCliente({ ...editandoCliente, nome_fantasia: v })} />
              <Campo rotulo="E-mail" tipo="email" valor={editandoCliente.email}
                     aoMudar={(v) => setEditandoCliente({ ...editandoCliente, email: v })} />
              <Campo rotulo="Responsável" valor={editandoCliente.responsavel}
                     aoMudar={(v) => setEditandoCliente({ ...editandoCliente, responsavel: v })} />
              <Campo rotulo="Telefone" valor={editandoCliente.telefone}
                     aoMudar={(v) => setEditandoCliente({ ...editandoCliente, telefone: v })} />
              <Campo rotulo="Tributos trabalhados" valor={editandoCliente.tributos_trabalhados}
                     aoMudar={(v) => setEditandoCliente({
                       ...editandoCliente, tributos_trabalhados: v })} />
            </div>
            <Campo rotulo="Observações" tipo="textarea" valor={editandoCliente.observacoes}
                   aoMudar={(v) => setEditandoCliente({ ...editandoCliente, observacoes: v })} />
            <Acoes>
              <button onClick={() => setEditandoCliente(null)}>Cancelar</button>
              <button className="primario" onClick={salvarCliente} disabled={ocupado}>Salvar</button>
            </Acoes>
          </div>
        </Modal>
      )}

      {formProc && (
        <Modal titulo={formProc.id ? "Editar procuração" : "Nova procuração"}
               aoFechar={() => setFormProc(null)} largura={620}>
          <div className="grade">
            <Aviso tipo="atencao">
              Lançar uma procuração à mão <b>não</b> a torna validada: o semáforo permanece
              <b> CINZA</b> até uma consulta bem-sucedida à fonte autorizada.
            </Aviso>
            <div className="grade g2">
              <Campo rotulo="Número da procuração" valor={formProc.numero}
                     aoMudar={(v) => setFormProc({ ...formProc, numero: v })} />
              <Campo rotulo="CPF/CNPJ do procurador" valor={formProc.procurador_doc}
                     aoMudar={(v) => setFormProc({ ...formProc, procurador_doc: v })} />
              <Campo rotulo="Início da vigência" tipo="date" valor={formProc.data_inicio}
                     aoMudar={(v) => setFormProc({ ...formProc, data_inicio: v })} />
              <Campo rotulo="Validade" tipo="date" valor={formProc.data_fim}
                     ajuda="Base para os alertas de 30, 15, 7 e 0 dias."
                     aoMudar={(v) => setFormProc({ ...formProc, data_fim: v })} />
            </div>
            <Campo rotulo="Observações" tipo="textarea" valor={formProc.observacoes}
                   aoMudar={(v) => setFormProc({ ...formProc, observacoes: v })} />
            <Acoes>
              <button onClick={() => setFormProc(null)}>Cancelar</button>
              <button className="primario" onClick={salvarProcuracao} disabled={ocupado}>
                {formProc.id ? "Salvar" : "Cadastrar"}
              </button>
            </Acoes>
          </div>
        </Modal>
      )}

      {formComp && (
        <Modal titulo={formComp.id ? "Editar PER/DCOMP" : "Nova PER/DCOMP"}
               aoFechar={() => setFormComp(null)} largura={680}>
          <div className="grade">
            <Aviso tipo="atencao">
              Aqui entram apenas os <b>dados declarados</b>. A situação da compensação muda somente
              por consulta à fonte ou pelo registro de resultado oficial, que gravam origem e data.
            </Aviso>
            <div className="grade g2">
              <Campo rotulo="Número da PER/DCOMP" valor={formComp.numero_perdcomp} obrigatorio
                     desabilitado={Boolean(formComp.id)}
                     aoMudar={(v) => setFormComp({ ...formComp, numero_perdcomp: v })} />
              <Campo rotulo="Tributo" valor={formComp.tributo}
                     aoMudar={(v) => setFormComp({ ...formComp, tributo: v })} />
              <Campo rotulo="Período de apuração" valor={formComp.periodo_apuracao}
                     placeholder="MM/AAAA"
                     aoMudar={(v) => setFormComp({ ...formComp, periodo_apuracao: v })} />
              <Campo rotulo="Data de transmissão" tipo="date" valor={formComp.data_transmissao}
                     aoMudar={(v) => setFormComp({ ...formComp, data_transmissao: v })} />
              <Campo rotulo="Valor do débito" valor={formComp.valor_debito} placeholder="0.00"
                     aoMudar={(v) => setFormComp({ ...formComp, valor_debito: v })} />
              <Campo rotulo="Crédito utilizado" valor={formComp.valor_credito} placeholder="0.00"
                     aoMudar={(v) => setFormComp({ ...formComp, valor_credito: v })} />
              <Campo rotulo="Situação da declaração" valor={formComp.situacao_declaracao}
                     placeholder="ATIVA, RETIFICADA…"
                     aoMudar={(v) => setFormComp({ ...formComp, situacao_declaracao: v })} />
            </div>
            <Campo rotulo="Observações" tipo="textarea" valor={formComp.observacoes}
                   aoMudar={(v) => setFormComp({ ...formComp, observacoes: v })} />
            <Acoes>
              <button onClick={() => setFormComp(null)}>Cancelar</button>
              <button className="primario" onClick={salvarCompensacao}
                      disabled={ocupado || !formComp.numero_perdcomp}>
                {formComp.id ? "Salvar" : "Cadastrar"}
              </button>
            </Acoes>
          </div>
        </Modal>
      )}
    </div>
  );
}
