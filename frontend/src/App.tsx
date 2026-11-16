import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./componentes/Layout";
import { Usuario, obterToken, obterUsuario } from "./lib/api";
import Alertas from "./paginas/Alertas";
import Auditoria from "./paginas/Auditoria";
import ClienteDetalhe from "./paginas/ClienteDetalhe";
import Clientes from "./paginas/Clientes";
import Compensacoes from "./paginas/Compensacoes";
import Importacao from "./paginas/Importacao";
import Integracoes from "./paginas/Integracoes";
import Login from "./paginas/Login";
import Monitoramento from "./paginas/Monitoramento";
import Painel from "./paginas/Painel";
import Procuracoes from "./paginas/Procuracoes";
import SituacaoFiscal from "./paginas/SituacaoFiscal";
import Usuarios from "./paginas/Usuarios";

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(obterUsuario());
  const local = useLocation();

  useEffect(() => { setUsuario(obterUsuario()); }, [local.pathname]);

  if (!obterToken() || !usuario) {
    return (
      <Routes>
        <Route path="/login" element={<Login aoEntrar={setUsuario} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout usuario={usuario}>
      <Routes>
        <Route path="/" element={<Painel />} />
        <Route path="/clientes" element={<Clientes />} />
        <Route path="/clientes/:id" element={<ClienteDetalhe />} />
        <Route path="/importacao" element={<Importacao />} />
        <Route path="/compensacoes" element={<Compensacoes />} />
        <Route path="/procuracoes" element={<Procuracoes />} />
        <Route path="/situacao-fiscal" element={<SituacaoFiscal />} />
        <Route path="/alertas" element={<Alertas />} />
        <Route path="/monitoramento" element={<Monitoramento perfil={usuario.perfil} />} />
        <Route path="/integracoes" element={<Integracoes />} />
        {usuario.perfil === "ADMIN" && <Route path="/usuarios" element={<Usuarios />} />}
        <Route path="/auditoria" element={<Auditoria />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<div className="vazio">Página não encontrada.</div>} />
      </Routes>
    </Layout>
  );
}
