import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Aviso, Cartao, Carregando, Kpi, Selo, Vazio } from "../componentes/ui";
import { api } from "../lib/api";
import { CORES, COR_CRITICIDADE, brl, data, numero, rotulo } from "../lib/formato";

interface Resumo {
  gerado_em: string;
  clientes: Record<string, number | string>;
  compensacoes: { total_monitoradas: number; por_situacao: Record<string, number>;
    valor_por_situacao: Record<string, string>; [k: string]: unknown };
  procuracoes: { total: number; ativas: number; proximas_vencimento: number;
    expiradas_ou_revogadas: number; situacao_desconhecida: number; semaforo: Record<string, number> };
  alertas: { abertos: number; por_criticidade: Record<string, number> };
  fontes: Record<string, string>;
}

interface Atencao {
  itens: { cliente_id: string; razao_social: string; cnpj: string; responsavel?: string;
    score: number; criticidade_maxima: string; qtd_alertas: number; motivos: string[];
    acao_sugerida: string }[];
}

const CORES_SITUACAO: Record<string, string> = {
  HOMOLOGADA: CORES.verde, HOMOLOGADA_PARCIALMENTE: CORES.amarelo,
  NAO_HOMOLOGADA: CORES.vermelho, COM_EXIGENCIA: "#e67e22", EM_ANALISE: CORES.azul,
  EM_PROCESSAMENTO: CORES.azulClaro, TRANSMITIDA: CORES.marinho,
  CANCELADA: CORES.cinza, SEM_INFORMACAO: "#9aa5b4",
};

export default function Painel() {
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [atencao, setAtencao] = useState<Atencao | null>(null);
  const [series, setSeries] = useState<{ debitos: { data: string; total_debitos: string }[] } | null>(null);
  const [filtroResponsavel, setFiltroResponsavel] = useState("");
  const [responsaveis, setResponsaveis] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const navegar = useNavigate();

  useEffect(() => { api.get<string[]>("/clientes/responsaveis").then(setResponsaveis).catch(() => {}); }, []);

  useEffect(() => {
    setResumo(null);
    Promise.all([
      api.get<Resumo>("/dashboard/resumo", { responsavel: filtroResponsavel }),
      api.get<Atencao>("/ia/clientes-atencao", { limite: 8 }),
      api.get<{ debitos: { data: string; total_debitos: string }[] }>("/dashboard/series", { dias: 120 }),
    ]).then(([r, a, s]) => { setResumo(r); setAtencao(a); setSeries(s); })
      .catch((e) => setErro(e.message));
  }, [filtroResponsavel]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!resumo) return <Carregando />;

  const comp = resumo.compensacoes;
  const dadosSituacao = Object.entries(comp.por_situacao)
    .filter(([, qtd]) => qtd > 0)
    .map(([situacao, qtd]) => ({ nome: rotulo(situacao), chave: situacao, valor: qtd }));
  const dadosValor = Object.entries(comp.valor_por_situacao)
    .filter(([chave]) => (comp.por_situacao[chave] ?? 0) > 0)
    .map(([chave, valor]) => ({ nome: rotulo(chave), chave, valor: Number(valor) }));
  const dadosDebitos = (series?.debitos ?? []).map((d) => ({
    data: data(d.data), valor: Number(d.total_debitos),
  }));

  return (
    <div className="grade">
      {resumo.fontes.aviso?.includes("simulador") && (
        <Aviso tipo="atencao">
          <b>Modo demonstração.</b> As fontes de dados estão em <b>simulador</b>: as informações são
          fictícias e não provêm da Receita Federal. Configure <code>MT_CONNECTOR_*</code> para usar
          fontes oficiais ou importação manual.
        </Aviso>
      )}

      <div className="filtros">
        <div className="campo">
          <label>Responsável</label>
          <select value={filtroResponsavel} onChange={(e) => setFiltroResponsavel(e.target.value)}>
            <option value="">Todos</option>
            {responsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <span style={{ fontSize: 12, color: "var(--cinza-500)" }}>
          Atualizado em {new Date(resumo.gerado_em).toLocaleString("pt-BR")}
        </span>
      </div>

      <div className="grade g4">
        <Kpi rotulo="Clientes cadastrados" valor={numero(Number(resumo.clientes.total))}
             nota={`${resumo.clientes.sem_consulta_atualizada} sem consulta atualizada`} />
        <Kpi rotulo="Compensações monitoradas" valor={numero(comp.total_monitoradas)}
             nota={`${comp.por_situacao.SEM_INFORMACAO ?? 0} sem informação atualizada`} cor="azul" />
        <Kpi rotulo="Homologadas" valor={numero(comp.por_situacao.HOMOLOGADA ?? 0)} cor="verde"
             nota={brl(comp.valor_por_situacao.HOMOLOGADA)} />
        <Kpi rotulo="Em análise / processamento" cor="azul"
             valor={numero((comp.por_situacao.EM_ANALISE ?? 0) + (comp.por_situacao.EM_PROCESSAMENTO ?? 0))} />
        <Kpi rotulo="Não homologadas" valor={numero(comp.por_situacao.NAO_HOMOLOGADA ?? 0)} cor="vermelho"
             nota={brl(comp.valor_por_situacao.NAO_HOMOLOGADA)} />
        <Kpi rotulo="Parciais / com exigência" cor="amarelo"
             valor={numero((comp.por_situacao.HOMOLOGADA_PARCIALMENTE ?? 0) + (comp.por_situacao.COM_EXIGENCIA ?? 0))} />
      </div>

      <div className="grade g4">
        <Kpi rotulo="Procurações ativas" valor={numero(resumo.procuracoes.ativas)} cor="verde" />
        <Kpi rotulo="Próximas do vencimento" valor={numero(resumo.procuracoes.proximas_vencimento)} cor="amarelo" />
        <Kpi rotulo="Expiradas / revogadas" valor={numero(resumo.procuracoes.expiradas_ou_revogadas)} cor="vermelho" />
        <Kpi rotulo="Situação desconhecida" valor={numero(resumo.procuracoes.situacao_desconhecida)} cor="cinza"
             nota="Sem validação por fonte autorizada" />
        <Kpi rotulo="Clientes com débitos" valor={numero(Number(resumo.clientes.com_debitos_em_aberto))}
             cor="vermelho" nota={brl(resumo.clientes.total_debitos_em_aberto as string)} />
        <Kpi rotulo="Sem pendências identificadas" cor="verde"
             valor={numero(Number(resumo.clientes.sem_pendencias_identificadas))} />
        <Kpi rotulo="Consulta indisponível" cor="amarelo"
             valor={numero(Number(resumo.clientes.consulta_indisponivel))}
             nota="Indisponibilidade ≠ regularidade" />
        <Kpi rotulo="Alertas abertos" valor={numero(resumo.alertas.abertos)} cor="vermelho"
             nota={Object.entries(resumo.alertas.por_criticidade)
               .filter(([, q]) => q > 0).map(([c, q]) => `${q} ${c.toLowerCase()}`).join(" · ")} />
      </div>

      <div className="grade g2">
        <Cartao titulo="Compensações por situação" descricao="Quantidade de PER/DCOMP em cada classificação">
          {dadosSituacao.length === 0 ? <Vazio>Sem compensações cadastradas.</Vazio> : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={dadosSituacao} dataKey="valor" nameKey="nome" innerRadius={55} outerRadius={95}
                     paddingAngle={2} isAnimationActive={false}>
                  {dadosSituacao.map((item) => (
                    <Cell key={item.chave} fill={CORES_SITUACAO[item.chave] ?? CORES.cinza} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number, n) => [`${v} PER/DCOMP`, n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Cartao>

        <Cartao titulo="Valor de crédito por situação" descricao="Soma dos valores informados de compensação">
          {dadosValor.length === 0 ? <Vazio>Sem dados.</Vazio> : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={dadosValor} margin={{ left: 8, right: 8, top: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef1f6" />
                <XAxis dataKey="nome" tick={{ fontSize: 10 }} interval={0} angle={-18} height={54} dy={10} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v: number) => brl(v)} />
                <Bar dataKey="valor" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {dadosValor.map((item) => (
                    <Cell key={item.chave} fill={CORES_SITUACAO[item.chave] ?? CORES.azul} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Cartao>
      </div>

      <Cartao titulo="Evolução dos débitos consultados"
              descricao="Somatório por dia de consulta — variação não implica causalidade com as compensações">
        {dadosDebitos.length < 2 ? (
          <Vazio>São necessárias pelo menos duas consultas para montar a série histórica.</Vazio>
        ) : (
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={dadosDebitos}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef1f6" />
              <XAxis dataKey="data" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(v: number) => brl(v)} />
              <Line type="monotone" dataKey="valor" stroke={CORES.marinho} strokeWidth={2} isAnimationActive={false}
                    dot={{ r: 3, fill: CORES.azul }} name="Total de débitos" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Cartao>

      <Cartao titulo="Clientes que exigem atenção"
              descricao="Ordenados pela gravidade acumulada dos alertas abertos (critério estatístico, não jurídico)"
              semPadding>
        {!atencao || atencao.itens.length === 0 ? <Vazio>Nenhum alerta aberto.</Vazio> : (
          <table>
            <thead>
              <tr>
                <th>Cliente</th><th>Responsável</th><th className="num">Alertas</th>
                <th>Criticidade</th><th>Motivos</th><th>Ação sugerida</th>
              </tr>
            </thead>
            <tbody>
              {atencao.itens.map((item) => (
                <tr key={item.cliente_id} className="clicavel"
                    onClick={() => navegar(`/clientes/${item.cliente_id}`)}>
                  <td>
                    <b style={{ color: "var(--marinho)" }}>{item.razao_social}</b>
                    <div className="mono" style={{ color: "var(--cinza-500)" }}>{item.cnpj}</div>
                  </td>
                  <td>{item.responsavel ?? "—"}</td>
                  <td className="num">{item.qtd_alertas}</td>
                  <td><Selo cor={COR_CRITICIDADE[item.criticidade_maxima]}>{item.criticidade_maxima}</Selo></td>
                  <td style={{ fontSize: 12 }}>{item.motivos.map((m) => rotulo(m)).join(" · ")}</td>
                  <td style={{ fontSize: 12, color: "var(--cinza-500)" }}>{item.acao_sugerida}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>
    </div>
  );
}
