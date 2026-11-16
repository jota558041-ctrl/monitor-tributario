import { ReactNode } from "react";

export function Cartao({ titulo, acoes, children, semPadding, descricao }: {
  titulo?: ReactNode; acoes?: ReactNode; children: ReactNode;
  semPadding?: boolean; descricao?: string;
}) {
  return (
    <section className="cartao">
      {titulo && (
        <header>
          <div>
            <h2>{titulo}</h2>
            {descricao && <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--cinza-500)" }}>{descricao}</p>}
          </div>
          {acoes && <div className="acoes">{acoes}</div>}
        </header>
      )}
      <div className={`corpo${semPadding ? " sem-padding" : ""}`}>{children}</div>
    </section>
  );
}

export function Kpi({ rotulo, valor, nota, cor = "azul" }: {
  rotulo: string; valor: ReactNode; nota?: string; cor?: "azul" | "verde" | "amarelo" | "vermelho" | "cinza";
}) {
  return (
    <div className={`kpi ${cor}`}>
      <div className="rotulo">{rotulo}</div>
      <div className="valor">{valor}</div>
      {nota && <div className="nota">{nota}</div>}
    </div>
  );
}

export function Selo({ cor = "cinza", children, titulo }: {
  cor?: string; children: ReactNode; titulo?: string;
}) {
  return <span className={`selo ${cor}`} title={titulo}>{children}</span>;
}

export function PontoSemaforo({ valor }: { valor: string }) {
  return <span className={`ponto ${valor}`} title={valor} />;
}

export function Aviso({ tipo = "info", children }: { tipo?: "info" | "atencao" | "erro" | "ok"; children: ReactNode }) {
  return <div className={`aviso ${tipo}`}>{children}</div>;
}

export function Carregando({ texto = "Carregando..." }: { texto?: string }) {
  return (
    <div className="vazio">
      <span className="carregando" /> <span style={{ marginLeft: 8 }}>{texto}</span>
    </div>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return <div className="vazio">{children}</div>;
}

export function Modal({ titulo, children, aoFechar, largura }: {
  titulo: ReactNode; children: ReactNode; aoFechar: () => void; largura?: number;
}) {
  return (
    <div className="modal-fundo" onClick={aoFechar}>
      <div className="modal" style={largura ? { width: `min(${largura}px, 100%)` } : undefined}
           onClick={(e) => e.stopPropagation()}>
        <header><h2>{titulo}</h2><button onClick={aoFechar}>Fechar</button></header>
        <div className="corpo">{children}</div>
      </div>
    </div>
  );
}

export function Definicoes({ itens }: { itens: [string, ReactNode][] }) {
  return (
    <div className="lista-definicoes">
      {itens.map(([chave, valor]) => (
        <div key={chave}><span>{chave}</span><b>{valor ?? "—"}</b></div>
      ))}
    </div>
  );
}

export function Paginacao({ pagina, total, tamanho, aoMudar }: {
  pagina: number; total: number; tamanho: number; aoMudar: (p: number) => void;
}) {
  const paginas = Math.max(1, Math.ceil(total / tamanho));
  if (total === 0) return null;
  return (
    <div className="linha" style={{ padding: "12px 16px", justifyContent: "space-between" }}>
      <span style={{ fontSize: 12, color: "var(--cinza-500)" }}>
        {total} registro(s) · página {pagina} de {paginas}
      </span>
      <div className="linha">
        <button className="pequeno" disabled={pagina <= 1} onClick={() => aoMudar(pagina - 1)}>Anterior</button>
        <button className="pequeno" disabled={pagina >= paginas} onClick={() => aoMudar(pagina + 1)}>Próxima</button>
      </div>
    </div>
  );
}
