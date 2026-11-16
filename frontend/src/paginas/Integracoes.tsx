import { useEffect, useState } from "react";
import { Aviso, Cartao, Carregando, Selo } from "../componentes/ui";
import { api } from "../lib/api";
import { rotulo } from "../lib/formato";

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

export default function Integracoes() {
  const [dados, setDados] = useState<Status | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api.get<Status>("/integracoes/status").then(setDados).catch((e) => setErro(e.message));
  }, []);

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

      <Cartao titulo="Regras de ouro aplicadas no código">
        <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8, fontSize: 13 }}>
          {dados.regras_de_ouro.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </Cartao>
    </div>
  );
}
