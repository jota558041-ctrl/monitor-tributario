"""Carga demonstrativa completa.

Executa o mesmo caminho que um usuário real percorreria:
 1. cria organização e usuários (ADMIN, ANALISTA, AUDITOR);
 2. gera a planilha de teste em data/;
 3. importa a planilha pelo serviço de importação (com validação e correções);
 4. ajusta o 'mundo fiscal' simulado para cobrir todos os cenários;
 5. roda o monitoramento (1ª consulta - linha de base);
 6. aplica mudanças (homologação, intimação, novo débito, revogação...);
 7. roda o monitoramento novamente - gera comparativos e alertas de mudança.

Uso:  python -m scripts.seed [--reset]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import UTC

from sqlalchemy import select  # noqa: E402

from app.core.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.models.alerta import RegraMonitoramento  # noqa: E402
from app.models.cliente import Cliente  # noqa: E402
from app.models.enums import (  # noqa: E402
    CanalNotificacao,
    Criticidade,
    Perfil,
    TipoMonitoramento,
)
from app.models.tenant import Organizacao, Usuario  # noqa: E402
from app.services import importacao as svc_import  # noqa: E402
from app.services import monitoramento as svc_monitor  # noqa: E402
from app.services import simulacao as svc_sim  # noqa: E402
from app.services.planilha import gerar_csv, gerar_modelo, gerar_planilha  # noqa: E402
from scripts.dados_demo import linhas_planilha, mapa_cnpj_perfil  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
DADOS = RAIZ / "data"

USUARIOS = [
    ("Administrador Demo", "admin@monitortributario.com.br", "Admin@123456", Perfil.ADMIN),
    ("Analista Demo", "analista@monitortributario.com.br", "Analista@123456", Perfil.ANALISTA),
    ("Auditor Demo", "auditor@monitortributario.com.br", "Auditor@123456", Perfil.AUDITOR),
]


def _retroagir(db, organizacao_id: str, *, dias: int, apenas_recentes: bool = False) -> None:
    """Recua no tempo as consultas já gravadas, criando um histórico plausível.

    Só é usado na carga demonstrativa: permite ver séries temporais e
    comparativos entre datas distintas sem esperar dias reais.
    """
    from datetime import timedelta

    from app.core.db import utcnow
    from app.models.compensacao import CompensacaoEvento
    from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
    from app.models.procuracao import ProcuracaoConsulta

    corte = utcnow() - timedelta(hours=1)
    delta = timedelta(days=dias)

    def recente(valor) -> bool:
        """SQLite devolve datas sem fuso; normaliza antes de comparar."""
        if valor is None:
            return False
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=UTC)
        return valor >= corte

    snaps = db.scalars(select(SituacaoFiscalSnapshot).where(
        SituacaoFiscalSnapshot.organizacao_id == organizacao_id)).all()
    for snap in snaps:
        if apenas_recentes and not recente(snap.consultado_em):
            continue
        snap.consultado_em = snap.consultado_em - delta
    for comparativo in db.scalars(select(SituacaoFiscalComparativo).where(
            SituacaoFiscalComparativo.organizacao_id == organizacao_id)).all():
        if apenas_recentes and not recente(comparativo.created_at):
            continue
        comparativo.created_at = comparativo.created_at - delta
    for consulta in db.scalars(select(ProcuracaoConsulta)).all():
        if apenas_recentes and not recente(consulta.consultado_em):
            continue
        consulta.consultado_em = consulta.consultado_em - delta
    for evento in db.scalars(select(CompensacaoEvento)).all():
        if apenas_recentes and not recente(evento.registrado_em):
            continue
        evento.registrado_em = evento.registrado_em - delta
        if evento.ocorrido_em:
            evento.ocorrido_em = evento.ocorrido_em - delta
    db.flush()


def _ajustar_cenarios(db, clientes: dict[str, Cliente]) -> None:
    perfis = mapa_cnpj_perfil()
    for cnpj, perfil in perfis.items():
        cliente = clientes.get(cnpj)
        if cliente is None:
            continue
        estado = svc_sim.semear_estado_de_cliente(db, cliente, sobrescrever=True)
        fiscal = dict(estado.situacao_fiscal)
        comps = dict(estado.compensacoes)
        procs = dict(estado.procuracoes)
        chave_comp = next((k for k in comps if k != "forcar"), None)

        if perfil == "REGULAR_HOMOLOGADA":
            fiscal = {"situacao_geral": "REGULAR", "pendencias": [],
                      "relatorio_bruto": "Nenhuma pendência encontrada (fictício)."}
            for k in [c for c in comps if c != "forcar"]:
                comps[k] = {**comps[k], "situacao_compensacao": "HOMOLOGADA",
                            "tem_despacho_decisorio": True,
                            "valor_compensado": comps[k].get("valor_credito"),
                            "resultado_analise": "Homologada integralmente (fictício)."}
        elif perfil == "COM_DEBITOS":
            fiscal = {"situacao_geral": "COM_PENDENCIAS", "pendencias": [
                {"categoria": "DEBITO_FEDERAL", "codigo": "2089-10", "periodo": "05/2024",
                 "descricao": "IRPJ declarado em DCTF e não pago", "valor": "15000.00",
                 "situacao": "DEVEDOR"},
                {"categoria": "DEBITO_PREVIDENCIARIO", "codigo": "1138-01", "periodo": "06/2024",
                 "descricao": "Contribuição previdenciária patronal", "valor": "4800.00",
                 "situacao": "EM COBRANÇA"},
            ], "relatorio_bruto": "Relatório fictício com pendências."}
        elif perfil == "PROCURACAO_VENCIDA":
            for k in list(procs):
                if k != "forcar":
                    procs[k] = {**procs[k], "situacao": "EXPIRADA"}
        elif perfil == "PROCURACAO_REVOGADA":
            for k in list(procs):
                if k != "forcar":
                    procs[k] = {**procs[k], "situacao": "REVOGADA"}
        elif perfil == "FONTE_INDISPONIVEL":
            fiscal["forcar"] = "INDISPONIVEL"
            comps["forcar"] = "INDISPONIVEL"
        elif perfil == "SEM_PODERES":
            fiscal["forcar"] = "NAO_AUTORIZADO"
        elif perfil == "NAO_HOMOLOGADA":
            if chave_comp:
                credito = comps[chave_comp].get("valor_credito")
                comps[chave_comp] = {**comps[chave_comp],
                                     "situacao_compensacao": "NAO_HOMOLOGADA",
                                     "tem_despacho_decisorio": True,
                                     "numero_despacho": "DD-778899",
                                     "valor_nao_homologado": credito,
                                     "resultado_analise": "Crédito não reconhecido (fictício)."}
            fiscal = {"situacao_geral": "COM_PENDENCIAS", "pendencias": [
                {"categoria": "DEBITO_EM_COBRANCA", "codigo": "5002-11", "periodo": "08/2024",
                 "descricao": "Débito reativado por não homologação de compensação",
                 "valor": "310000.00", "situacao": "EM COBRANÇA"},
            ], "relatorio_bruto": "Relatório fictício."}
        elif perfil == "COM_EXIGENCIA":
            if chave_comp:
                comps[chave_comp] = {**comps[chave_comp],
                                     "situacao_compensacao": "COM_EXIGENCIA",
                                     "tem_intimacao": True,
                                     "resultado_analise": "Intimação para apresentar documentos."}
        elif perfil == "PARCELAMENTO":
            fiscal = {"situacao_geral": "COM_PENDENCIAS", "pendencias": [
                {"categoria": "PARCELAMENTO", "codigo": "PARC-2023-55", "periodo": "2023",
                 "descricao": "Parcelamento ordinário em andamento", "valor": "88000.00",
                 "situacao": "ATIVO"},
                {"categoria": "OBRIGACAO_ACESSORIA", "codigo": "DCTFWEB-OMISSA",
                 "periodo": "09/2025", "descricao": "Omissão de entrega de DCTFWeb",
                 "valor": "0", "situacao": "PENDENTE"},
                {"categoria": "DEBITO_SUSPENSO", "codigo": "9001-02", "periodo": "07/2024",
                 "descricao": "Débito com exigibilidade suspensa (processo judicial)",
                 "valor": "42000.00", "situacao": "SUSPENSO"},
            ], "relatorio_bruto": "Relatório fictício."}

        estado.situacao_fiscal = fiscal
        estado.compensacoes = comps
        estado.procuracoes = procs
        estado.nota = f"Cenário demonstrativo: {perfil}"
    db.flush()


def executar(reset: bool = False) -> dict[str, object]:
    DADOS.mkdir(parents=True, exist_ok=True)
    if reset:
        Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        org = db.scalar(select(Organizacao).where(Organizacao.nome == "Escritório Demonstração"))
        if org is None:
            org = Organizacao(nome="Escritório Demonstração", cnpj="19131243000197")
            db.add(org)
            db.flush()

        for nome, email, senha, perfil in USUARIOS:
            if db.scalar(select(Usuario).where(Usuario.email == email)) is None:
                db.add(Usuario(organizacao_id=org.id, nome=nome, email=email,
                               senha_hash=hash_senha(senha), perfil=str(perfil)))
        db.flush()
        admin = db.scalar(select(Usuario).where(Usuario.email == "admin@monitortributario.com.br"))

        # ---- planilhas de teste ------------------------------------------
        linhas = linhas_planilha()
        xlsx = gerar_planilha(linhas, titulo="Clientes")
        (DADOS / "planilha-teste-clientes.xlsx").write_bytes(xlsx)
        (DADOS / "planilha-teste-clientes.csv").write_bytes(gerar_csv(linhas))
        (DADOS / "modelo-importacao.xlsx").write_bytes(gerar_modelo())

        # ---- importação pelo pipeline real ------------------------------
        importacao = svc_import.criar_importacao(
            db, organizacao_id=org.id, usuario_id=admin.id, usuario_email=admin.email,
            nome_arquivo="planilha-teste-clientes.xlsx", conteudo=xlsx,
        )
        resumo_import = svc_import.confirmar(
            db, importacao, usuario_id=admin.id, usuario_email=admin.email,
            criar_estado_simulado=True,
        )

        clientes = {c.cnpj: c for c in db.scalars(
            select(Cliente).where(Cliente.organizacao_id == org.id)
        )}
        _ajustar_cenarios(db, clientes)

        # ---- regras de monitoramento ------------------------------------
        if not db.scalars(select(RegraMonitoramento)
                          .where(RegraMonitoramento.organizacao_id == org.id)).first():
            db.add_all([
                RegraMonitoramento(
                    organizacao_id=org.id, nome="Monitoramento diário completo",
                    tipo_monitoramento=str(TipoMonitoramento.COMPLETO), cron="0 6 * * *",
                    criticidade_minima=str(Criticidade.BAIXA),
                    canais=[str(CanalNotificacao.SISTEMA)],
                ),
                RegraMonitoramento(
                    organizacao_id=org.id, nome="Procurações - duas vezes ao dia",
                    tipo_monitoramento=str(TipoMonitoramento.PROCURACOES), cron="0 8,18 * * *",
                    criticidade_minima=str(Criticidade.MEDIA),
                    canais=[str(CanalNotificacao.SISTEMA), str(CanalNotificacao.EMAIL)],
                    destinatarios=["fiscal@escritorio-demo.local"],
                ),
                RegraMonitoramento(
                    organizacao_id=org.id, nome="Situação fiscal - semanal",
                    tipo_monitoramento=str(TipoMonitoramento.SITUACAO_FISCAL), cron="0 7 * * 1",
                    criticidade_minima=str(Criticidade.ALTA),
                    canais=[str(CanalNotificacao.SISTEMA)],
                ),
            ])
        db.commit()

        # ---- 1ª passagem: linha de base (exclui o cliente 'nunca consultado')
        perfis = mapa_cnpj_perfil()
        nunca = [c.id for cnpj, c in clientes.items() if perfis.get(cnpj) == "NUNCA_CONSULTADO"]
        monitorar = [c.id for c in clientes.values() if c.id not in nunca]
        exec1 = svc_monitor.executar(
            db, organizacao_id=org.id, clientes_ids=monitorar,
            acionada_por="SEED:linha-de-base",
        )
        db.commit()
        _retroagir(db, org.id, dias=14)   # a linha de base passa a ser de 14 dias atrás

        # ---- mudanças para disparar alertas -----------------------------
        cenarios_aplicados = []
        por_perfil = {perfis.get(cnpj): c for cnpj, c in clientes.items()}
        plano = [
            ("REGULAR_HOMOLOGADA", "REVERTER_HOMOLOGACAO", None),
            ("COM_DEBITOS", "REDUZIR_DEBITO", {"fator": "0.3333"}),
            ("PROCURACAO_REVOGADA", "REVOGAR_PROCURACAO", None),
            ("COM_EXIGENCIA", "EMITIR_INTIMACAO", {"dias": 20}),
            ("PARCELAMENTO", "NOVO_DEBITO", {"valor": "9800.00",
                                             "descricao": "Débito identificado após compensação"}),
            ("NAO_HOMOLOGADA", "HOMOLOGAR_PARCIALMENTE", None),
        ]
        for perfil, cenario, params in plano:
            cliente = por_perfil.get(perfil)
            if cliente is None:
                continue
            try:
                cenarios_aplicados.append(
                    svc_sim.aplicar_cenario(db, cliente, cenario, params)
                )
            except ValueError as exc:
                cenarios_aplicados.append({"cenario": cenario, "erro": str(exc)})
        db.commit()

        # ---- 2ª passagem: detecta mudanças ------------------------------
        exec2 = svc_monitor.executar(
            db, organizacao_id=org.id, clientes_ids=monitorar,
            acionada_por="SEED:apos-mudancas",
        )
        db.commit()
        _retroagir(db, org.id, dias=7, apenas_recentes=True)

        # ---- 3ª passagem: nova rodada de mudanças (série histórica) ------
        plano2 = [
            ("COM_DEBITOS", "NOVO_DEBITO", {"valor": "12400.00",
                                            "descricao": "Débito federal identificado na última consulta"}),
            ("NAO_HOMOLOGADA", "EMITIR_INTIMACAO", {"dias": 15}),
            ("PARCELAMENTO", "REDUZIR_DEBITO", {"fator": "0.4"}),
            ("PROCURACAO_VENCIDA", "RENOVAR_PROCURACAO", None),
            ("FONTE_INDISPONIVEL", "RESTAURAR_FONTE", None),
        ]
        for perfil, cenario, params in plano2:
            cliente = por_perfil.get(perfil)
            if cliente is None:
                continue
            try:
                cenarios_aplicados.append(svc_sim.aplicar_cenario(db, cliente, cenario, params))
            except ValueError as exc:
                cenarios_aplicados.append({"cenario": cenario, "erro": str(exc)})
        db.commit()

        exec3 = svc_monitor.executar(
            db, organizacao_id=org.id, clientes_ids=monitorar,
            acionada_por="SEED:rodada-atual",
        )
        db.commit()

        from app.models.alerta import Alerta
        from app.models.compensacao import Compensacao
        from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
        from app.models.procuracao import Procuracao

        contagem = {
            "clientes": len(clientes),
            "procuracoes": len(list(db.scalars(select(Procuracao)))),
            "compensacoes": len(list(db.scalars(select(Compensacao)))),
            "snapshots": len(list(db.scalars(select(SituacaoFiscalSnapshot)))),
            "comparativos": len(list(db.scalars(select(SituacaoFiscalComparativo)))),
            "alertas": len(list(db.scalars(select(Alerta)))),
        }
        return {
            "organizacao": org.nome,
            "usuarios": [(u[1], u[2], str(u[3])) for u in USUARIOS],
            "resumo_importacao": resumo_import,
            "execucao_1": {"id": exec1.id, "alertas": exec1.alertas_gerados,
                           "ok": exec1.consultas_ok,
                           "indisponiveis": exec1.consultas_indisponiveis,
                           "nao_autorizadas": exec1.consultas_nao_autorizadas},
            "cenarios_aplicados": cenarios_aplicados,
            "execucao_2": {"id": exec2.id, "alertas": exec2.alertas_gerados,
                           "mudancas": exec2.mudancas_detectadas},
            "execucao_3": {"id": exec3.id, "alertas": exec3.alertas_gerados,
                           "mudancas": exec3.mudancas_detectadas},
            "contagem": contagem,
            "arquivos": [str(DADOS / "planilha-teste-clientes.xlsx"),
                         str(DADOS / "planilha-teste-clientes.csv"),
                         str(DADOS / "modelo-importacao.xlsx")],
        }
    finally:
        db.close()


if __name__ == "__main__":
    import json

    resultado = executar(reset="--reset" in sys.argv)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
