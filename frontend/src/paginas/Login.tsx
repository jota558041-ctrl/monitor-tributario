import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Aviso } from "../componentes/ui";
import { Usuario, api } from "../lib/api";

export default function Login({ aoEntrar }: { aoEntrar: (u: Usuario) => void }) {
  const [email, setEmail] = useState("admin@monitortributario.com.br");
  const [senha, setSenha] = useState("Admin@123456");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const navegar = useNavigate();

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    setCarregando(true);
    setErro(null);
    try {
      const usuario = await api.login(email, senha);
      aoEntrar(usuario);
      navegar("/");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha no login.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="login-tela">
      <div className="login-arte">
        <div className="marca" style={{ padding: 0 }}>
          <div className="logo">MT</div>
          <div><b style={{ fontSize: 16 }}>Monitor Tributário</b><span>Plataforma de monitoramento fiscal</span></div>
        </div>
        <h2>Compensações, procurações e situação fiscal sob controle.</h2>
        <ul>
          <li>Importação de planilhas com validação de CNPJ e correção assistida</li>
          <li>PER/DCOMP com histórico de situação — transmissão não é homologação</li>
          <li>Semáforo de procurações, validado por fonte autorizada</li>
          <li>Comparação entre consultas: novos débitos, baixados e remanescentes</li>
          <li>Alertas explicáveis, com fonte e data/hora de cada consulta</li>
        </ul>
        <p style={{ fontSize: 12, color: "#9fb6d6" }}>
          Ambiente de demonstração com dados fictícios. Nenhuma informação provém da Receita Federal.
        </p>
      </div>

      <div className="login-form">
        <form className="caixa" onSubmit={enviar}>
          <div>
            <h1>Entrar</h1>
            <p style={{ color: "var(--cinza-500)", fontSize: 13 }}>Acesse com suas credenciais.</p>
          </div>
          {erro && <Aviso tipo="erro">{erro}</Aviso>}
          <div>
            <label htmlFor="email">E-mail</label>
            <input id="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
          </div>
          <div>
            <label htmlFor="senha">Senha</label>
            <input id="senha" type="password" value={senha} onChange={(e) => setSenha(e.target.value)}
                   autoComplete="current-password" />
          </div>
          <button className="primario" type="submit" disabled={carregando}>
            {carregando ? <span className="carregando" /> : null} Entrar
          </button>
          <div className="credenciais">
            <b>Credenciais de demonstração</b><br />
            admin@monitortributario.com.br / Admin@123456 (administrador)<br />
            analista@monitortributario.com.br / Analista@123456 (analista)<br />
            auditor@monitortributario.com.br / Auditor@123456 (somente leitura)
          </div>
        </form>
      </div>
    </div>
  );
}
