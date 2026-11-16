import { ReactNode, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Usuario, api, limparSessao } from "../lib/api";

const MENU: { grupo: string; itens: { rota: string; nome: string; icone: string;
  somenteAdmin?: boolean }[] }[] = [
  {
    grupo: "Visão geral",
    itens: [
      { rota: "/", nome: "Painel", icone: "▦" },
      { rota: "/alertas", nome: "Alertas", icone: "⚠" },
    ],
  },
  {
    grupo: "Cadastro",
    itens: [
      { rota: "/clientes", nome: "Clientes", icone: "☰" },
      { rota: "/importacao", nome: "Importar planilha", icone: "⇪" },
    ],
  },
  {
    grupo: "Monitoramento",
    itens: [
      { rota: "/compensacoes", nome: "Compensações", icone: "⇄" },
      { rota: "/procuracoes", nome: "Procurações", icone: "✇" },
      { rota: "/situacao-fiscal", nome: "Situação fiscal", icone: "₪" },
      { rota: "/monitoramento", nome: "Execuções e regras", icone: "⟳" },
    ],
  },
  {
    grupo: "Governança",
    itens: [
      { rota: "/integracoes", nome: "Fontes de dados", icone: "⛓" },
      { rota: "/auditoria", nome: "Auditoria", icone: "✓" },
      { rota: "/usuarios", nome: "Usuários", icone: "⚇", somenteAdmin: true },
    ],
  },
];

const TITULOS: Record<string, { titulo: string; sub: string }> = {
  "/": { titulo: "Painel de monitoramento", sub: "Indicadores consolidados de clientes, compensações, procurações e situação fiscal" },
  "/alertas": { titulo: "Alertas", sub: "Ocorrências detectadas, com explicação, fonte e data da consulta" },
  "/clientes": { titulo: "Clientes", sub: "Cadastro, histórico de alterações e consultas por cliente" },
  "/importacao": { titulo: "Importação de planilha", sub: "Detecção de colunas, validação, correção e confirmação" },
  "/compensacoes": { titulo: "Compensações (PER/DCOMP)", sub: "Situação, despacho decisório, intimações e histórico de evolução" },
  "/procuracoes": { titulo: "Procurações eletrônicas", sub: "Semáforo de validade — situação só é considerada após validação por fonte" },
  "/situacao-fiscal": { titulo: "Situação fiscal", sub: "Snapshots por consulta e comparação entre períodos" },
  "/monitoramento": { titulo: "Monitoramento", sub: "Execuções, agendamentos e simulador de mudanças" },
  "/integracoes": { titulo: "Fontes de dados", sub: "Capacidades, limitações, prontidão para produção e amostras de homologação" },
  "/auditoria": { titulo: "Trilha de auditoria", sub: "Quem acessou ou alterou cada informação" },
  "/usuarios": { titulo: "Usuários", sub: "Perfis de acesso, ativação e redefinição de senha" },
};

export default function Layout({ usuario, children }: { usuario: Usuario; children: ReactNode }) {
  const navegar = useNavigate();
  const local = useLocation();
  const [abertos, setAbertos] = useState<number>(0);

  useEffect(() => {
    api.get<{ total: number }>("/alertas", { status: "NOVO", tamanho: 1 })
      .then((d) => setAbertos(d.total)).catch(() => setAbertos(0));
  }, [local.pathname]);

  const base = "/" + (local.pathname.split("/")[1] ?? "");
  const cabecalho = TITULOS[base === "/" ? "/" : base] ?? { titulo: "Monitor Tributário", sub: "" };

  function sair() {
    limparSessao();
    navegar("/login");
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="marca">
          <div className="logo">MT</div>
          <div><b>Monitor Tributário</b><span>Compensações · Procurações · RFB</span></div>
        </div>
        {MENU.map((grupo) => (
          <div key={grupo.grupo}>
            <div className="nav-grupo">{grupo.grupo}</div>
            {grupo.itens.filter((item) => !item.somenteAdmin || usuario.perfil === "ADMIN")
              .map((item) => (
              <button
                key={item.rota}
                className={`nav-item${(item.rota === "/" ? local.pathname === "/" : local.pathname.startsWith(item.rota)) ? " ativo" : ""}`}
                onClick={() => navegar(item.rota)}
              >
                <span style={{ width: 16, textAlign: "center", opacity: .85 }}>{item.icone}</span>
                {item.nome}
                {item.rota === "/alertas" && abertos > 0 && <span className="pino">{abertos}</span>}
              </button>
            ))}
          </div>
        ))}
        <div className="rodape-sidebar">
          Dados de demonstração.<br />Nenhuma informação provém da Receita Federal.
        </div>
      </aside>

      <div className="conteudo">
        <header className="topbar">
          <div className="titulo">
            <h1>{cabecalho.titulo}</h1>
            <p>{cabecalho.sub}</p>
          </div>
          <div className="usuario">
            <div className="avatar">{usuario.nome.slice(0, 2).toUpperCase()}</div>
            <div style={{ lineHeight: 1.25 }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{usuario.nome}</div>
              <div style={{ fontSize: 11, color: "var(--cinza-500)" }}>{usuario.perfil}</div>
            </div>
            <button className="pequeno" onClick={sair}>Sair</button>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
