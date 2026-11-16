import { useEffect, useState } from "react";
import { Acoes, Aviso, Campo, Cartao, Carregando, Modal, Selo, Vazio } from "../componentes/ui";
import { Usuario, api } from "../lib/api";
import { dataHora } from "../lib/formato";

const PERFIS = [
  { valor: "ANALISTA", rotulo: "Analista — escrita operacional" },
  { valor: "ADMIN", rotulo: "Administrador — acesso total" },
  { valor: "AUDITOR", rotulo: "Auditor — somente leitura" },
];

const VAZIO = { nome: "", email: "", senha: "", perfil: "ANALISTA" };

export default function Usuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null);
  const [novo, setNovo] = useState({ ...VAZIO });
  const [criando, setCriando] = useState(false);
  const [redefinindo, setRedefinindo] = useState<Usuario | null>(null);
  const [novaSenha, setNovaSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  function carregar() {
    api.get<Usuario[]>("/usuarios").then(setUsuarios).catch((e) => setErro(e.message));
  }
  useEffect(carregar, []);

  async function criar() {
    setErro(null);
    try {
      await api.post("/usuarios", novo);
      setNovo({ ...VAZIO });
      setCriando(false);
      setMensagem(`Usuário ${novo.email} criado.`);
      carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao criar usuário."); }
  }

  async function alternarAtivo(usuario: Usuario) {
    await api.patch(`/usuarios/${usuario.id}`, { ativo: !usuario.ativo });
    carregar();
  }

  async function mudarPerfil(usuario: Usuario, perfil: string) {
    await api.patch(`/usuarios/${usuario.id}`, { perfil });
    carregar();
  }

  async function redefinirSenha() {
    if (!redefinindo) return;
    setErro(null);
    try {
      await api.patch(`/usuarios/${redefinindo.id}`, { senha: novaSenha });
      setMensagem(`Senha de ${redefinindo.email} redefinida. O usuário deverá trocá-la no próximo acesso.`);
      setRedefinindo(null);
      setNovaSenha("");
      carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao redefinir senha."); }
  }

  return (
    <div className="grade">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {mensagem && <Aviso tipo="ok">{mensagem}</Aviso>}
      <Aviso tipo="info">
        <b>Perfis.</b> <b>Administrador</b>: acesso total, incluindo usuários e regras.{" "}
        <b>Analista</b>: importa, cadastra, consulta fontes e trata alertas.{" "}
        <b>Auditor</b>: somente leitura, inclusive da trilha de auditoria.
        A senha exige 10 caracteres, com letra, número e caractere especial.
      </Aviso>

      <Cartao titulo="Usuários da organização" semPadding
              acoes={<button className="primario pequeno" onClick={() => setCriando(true)}>
                Novo usuário</button>}>
        {!usuarios ? <Carregando /> : usuarios.length === 0 ? <Vazio>Nenhum usuário.</Vazio> : (
          <table>
            <thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Situação</th>
                        <th>Último acesso</th><th /></tr></thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id}>
                  <td><b style={{ color: "var(--marinho)" }}>{u.nome}</b></td>
                  <td style={{ fontSize: 12 }}>{u.email}</td>
                  <td>
                    <select value={u.perfil} style={{ width: 150, fontSize: 12, padding: "4px 8px" }}
                            onChange={(e) => mudarPerfil(u, e.target.value)}>
                      {PERFIS.map((p) => <option key={p.valor} value={p.valor}>{p.valor}</option>)}
                    </select>
                  </td>
                  <td>{u.ativo ? <Selo cor="verde">Ativo</Selo> : <Selo cor="cinza">Inativo</Selo>}</td>
                  <td style={{ fontSize: 12 }}>{dataHora(u.ultimo_login)}</td>
                  <td>
                    <div className="linha" style={{ gap: 4 }}>
                      <button className="link pequeno" onClick={() => setRedefinindo(u)}>
                        Redefinir senha
                      </button>
                      <button className="link pequeno" onClick={() => alternarAtivo(u)}>
                        {u.ativo ? "Desativar" : "Ativar"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      {criando && (
        <Modal titulo="Novo usuário" aoFechar={() => setCriando(false)} largura={560}>
          <div className="grade">
            <Campo rotulo="Nome" valor={novo.nome} obrigatorio
                   aoMudar={(v) => setNovo({ ...novo, nome: v })} />
            <Campo rotulo="E-mail" tipo="email" valor={novo.email} obrigatorio
                   aoMudar={(v) => setNovo({ ...novo, email: v })} />
            <Campo rotulo="Perfil" tipo="select" valor={novo.perfil} opcoes={PERFIS}
                   aoMudar={(v) => setNovo({ ...novo, perfil: v })} />
            <Campo rotulo="Senha inicial" tipo="password" valor={novo.senha} obrigatorio
                   ajuda="Mínimo de 10 caracteres, com letra, número e caractere especial."
                   aoMudar={(v) => setNovo({ ...novo, senha: v })} />
            <Acoes>
              <button onClick={() => setCriando(false)}>Cancelar</button>
              <button className="primario" onClick={criar}
                      disabled={!novo.nome || !novo.email || !novo.senha}>Criar usuário</button>
            </Acoes>
          </div>
        </Modal>
      )}

      {redefinindo && (
        <Modal titulo={`Redefinir senha — ${redefinindo.nome}`} aoFechar={() => setRedefinindo(null)}
               largura={520}>
          <div className="grade">
            <Aviso tipo="atencao">
              O usuário será marcado para trocar a senha no próximo acesso. A ação fica registrada
              na trilha de auditoria.
            </Aviso>
            <Campo rotulo="Nova senha" tipo="password" valor={novaSenha} obrigatorio
                   ajuda="Mínimo de 10 caracteres, com letra, número e caractere especial."
                   aoMudar={setNovaSenha} />
            <Acoes>
              <button onClick={() => setRedefinindo(null)}>Cancelar</button>
              <button className="primario" onClick={redefinirSenha} disabled={!novaSenha}>
                Redefinir
              </button>
            </Acoes>
          </div>
        </Modal>
      )}
    </div>
  );
}
