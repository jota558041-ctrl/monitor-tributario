import { useEffect, useState } from "react";
import { Aviso, Cartao, Carregando, Kpi, Selo, Vazio } from "../componentes/ui";
import { api, obterUsuario } from "../lib/api";
import { dataHora, rotulo } from "../lib/formato";

interface Fonte {
  dominio: string; conector_configurado: string; nome: string; origem: string;
  automatizada: boolean; requer_certificado: boolean; requer_procuracao: boolean;
  poderes_necessarios: string[]; limitacoes: string[]; referencia?: string | null;
}
interface Status {
  fontes: Fonte[];
  integra_contador: { habilitado: boolean; configurado: boolean; motivo?: string | null;
    rate_limit_rpm: number };
  regras_de_ouro: string[];
  documentacao: string;
}

interface ItemProntidao {
  item: string; situacao: "OK" | "ATENCAO" | "CRITICO"; detalhe: string; recomendacao: string;
}
interface Prontidao {
  pronto_para_producao: boolean;
  resumo: { ok: number; atencao: number; critico: number; total: number };
  itens: ItemProntidao[];
  verificado_em: string;
  observacao: string;
}
interface Amostras {
  modo_homologacao_ativo: boolean; total: number; aviso: string;
  itens: { id: string; dominio: string; contribuinte?: string | null; id_sistema?: string | null;
    id_servico?: string | null; http_status?: number | null; disponibilidade?: string | null;
    duracao_ms?: number | null; erro?: string | null; created_at: string;
    requisicao?: unknown; resposta?: unknown }[];
}

const COR_SITUACAO: Record<string, string> = { OK: "verde", ATENCAO: "amarelo", CRITICO: "vermelho" };

export default function Integracoes() {
  const [dados, setDados] = useState<Status | null>(null);
  const [prontidao, setProntidao] = useState<Prontidao | null>(null);
  const [amostras, setAmostras] = useState<Amostras | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const admin = obterUsuario()?.perfil === "ADMIN";

  useEffect(() => {
    api.get<Status>("/integracoes/status").then(setDados).catch((e) => setErro(e.message));
    if (admin) {
      api.get<Prontidao>("/sistema/prontidao").then(setProntidao).catch(() => {});
      api.get<Amostras>("/sistema/amostras-integracao").then(setAmostras).catch(() => {});
    }
  }, [admin]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  return (
    <div className="grade">
      <Aviso tipo="info">
        <b>Transparência de origem.</b> Cada informação do sistema guarda a fonte, a data/hora da
        consulta e o estado técnico (OK, sem dados, indisponível, não autorizado, não consultado).
        Documentação técnica: <code>{dados.documentacao}</code>
      </Aviso>

      <div className="grade g3">
        {dados.fontes.map((f) => (
          <Cartao key={f.dominio} titulo={rotulo(f.dominio)} descricao={f.nome}>
            <div className="linha">
              <Selo cor={f.conector_configurado === "simulador" ? "amarelo"
                : f.conector_configurado === "manual" ? "cinza" : "verde"}>
                conector: {f.conector_configurado}
              </Selo>
              <Selo cor={f.automatizada ? "azul" : "cinza"}>
                {f.automatizada ? "Consulta automática" : "Sem automação"}
              </Selo>
              {f.requer_certificado && <Selo cor="azul">Certificado e-CNPJ</Selo>}
              {f.requer_procuracao && <Selo cor="azul">Procuração e-CAC</Selo>}
            </div>
            {f.poderes_necessarios.length > 0 && (
              <div className="espaco">
                <b style={{ fontSize: 12 }}>Poderes necessários</b>
                <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12 }}>
                  {f.poderes_necessarios.map((p) => <li key={p}>{p}</li>)}
                </ul>
              </div>
            )}
            <div className="espaco">
              <b style={{ fontSize: 12 }}>Limitações declaradas</b>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, lineHeight: 1.6 }}>
                {f.limitacoes.map((l) => <li key={l}>{l}</li>)}
              </ul>
            </div>
          </Cartao>
        ))}
      </div>

      <Cartao titulo="Integra Contador (SERPRO)"
              descricao="Adaptador presente, desativado por padrão — requer contrato, credenciais e certificado">
        <div className="linha">
          <Selo cor={dados.integra_contador.habilitado ? "verde" : "cinza"}>
            {dados.integra_contador.habilitado ? "Habilitado" : "Desabilitado"}
          </Selo>
          <Selo cor={dados.integra_contador.configurado ? "verde" : "amarelo"}>
            {dados.integra_contador.configurado ? "Configurado" : "Configuração incompleta"}
          </Selo>
          <Selo cor="azul">limite {dados.integra_contador.rate_limit_rpm} req/min</Selo>
        </div>
        {dados.integra_contador.motivo && (
          <div className="espaco"><Aviso tipo="atencao">{dados.integra_contador.motivo}</Aviso></div>
        )}
      </Cartao>

      {prontidao && (
        <Cartao titulo="Prontidão para produção" semPadding
                descricao={`Verificado em ${dataHora(prontidao.verificado_em)} — ${
                  prontidao.resumo.ok} OK, ${prontidao.resumo.atencao} atenção, ${
                  prontidao.resumo.critico} crítico`}>
          <div style={{ padding: 16 }}>
            <Aviso tipo={prontidao.pronto_para_producao ? "ok" : "atencao"}>
              {prontidao.pronto_para_producao
                ? "Nenhum impedimento crítico de configuração encontrado."
                : "Há itens críticos de configuração pendentes antes de liberar o acesso em produção."}
              {" "}{prontidao.observacao}
            </Aviso>
          </div>
          <table>
            <thead><tr><th>Item</th><th>Situação</th><th>Como está</th><th>Recomendação</th></tr></thead>
            <tbody>
              {prontidao.itens.map((i) => (
                <tr key={i.item}>
                  <td><b style={{ color: "var(--marinho)" }}>{i.item}</b></td>
                  <td><Selo cor={COR_SITUACAO[i.situacao]}>{rotulo(i.situacao)}</Selo></td>
                  <td style={{ fontSize: 12 }}>{i.detalhe}</td>
                  <td style={{ fontSize: 12, color: "var(--cinza-500)" }}>{i.recomendacao || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>
      )}

      {amostras && (
        <Cartao titulo="Amostras de homologação" semPadding
                descricao="Capturas de requisição e resposta das fontes, para mapear os campos do contrato"
                acoes={amostras.total > 0 ? (
                  <button className="pequeno" onClick={async () => {
                    if (!window.confirm("Apagar todas as amostras capturadas?")) return;
                    await api.delete("/sistema/amostras-integracao");
                    setAmostras(await api.get<Amostras>("/sistema/amostras-integracao"));
                  }}>Apagar amostras</button>
                ) : undefined}>
          <div style={{ padding: 16 }}>
            <Aviso tipo={amostras.modo_homologacao_ativo ? "atencao" : "info"}>
              Modo homologação:{" "}
              <b>{amostras.modo_homologacao_ativo ? "ATIVO" : "desligado"}</b>.{" "}
              {amostras.aviso}
            </Aviso>
          </div>
          {amostras.itens.length === 0 ? (
            <Vazio>
              Nenhuma amostra capturada. Ative <code>MT_INTEGRA_CONTADOR_MODO_HOMOLOGACAO</code>{" "}
              durante o mapeamento dos campos do contrato.
            </Vazio>
          ) : (
            <table>
              <thead><tr><th>Quando</th><th>Domínio</th><th>Serviço</th><th>Contribuinte</th>
                          <th>HTTP</th><th>Disponibilidade</th><th className="num">ms</th>
                          <th>Erro</th></tr></thead>
              <tbody>
                {amostras.itens.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontSize: 12 }}>{dataHora(a.created_at)}</td>
                    <td>{rotulo(a.dominio)}</td>
                    <td className="mono" style={{ fontSize: 11 }}>
                      {[a.id_sistema, a.id_servico].filter(Boolean).join(" / ") || "—"}
                    </td>
                    <td className="mono" style={{ fontSize: 11 }}>{a.contribuinte ?? "—"}</td>
                    <td>{a.http_status ?? "—"}</td>
                    <td style={{ fontSize: 11 }}>{rotulo(a.disponibilidade)}</td>
                    <td className="num">{a.duracao_ms ?? "—"}</td>
                    <td style={{ fontSize: 11, color: "var(--vermelho)" }}>{a.erro ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>
      )}

      <Cartao titulo="Regras de ouro aplicadas no código">
        <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8, fontSize: 13 }}>
          {dados.regras_de_ouro.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </Cartao>
    </div>
  );
}
