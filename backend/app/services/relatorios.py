"""Geração de relatórios em Excel (.xlsx) e PDF.

Todo relatório carrega, no rodapé ou em aba própria, a procedência da
informação: fonte, data da consulta e as ressalvas de interpretação. Um
relatório sem essa marcação seria uma afirmação sem lastro.
"""
from __future__ import annotations

import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alerta import Alerta
from app.models.cliente import Cliente
from app.models.compensacao import Compensacao, CompensacaoEvento
from app.models.enums import StatusAlerta
from app.models.fiscal import SituacaoFiscalComparativo, SituacaoFiscalSnapshot
from app.models.procuracao import Procuracao, ProcuracaoConsulta
from app.services.cnpj import formatar_cnpj
from app.services.fiscal import RESSALVA_PADRAO
from app.services.procuracoes import dias_para_vencer, semaforo

AZUL_MARINHO = "1B2A4A"
CINZA = "F2F4F8"
VERDE = "0F8A4D"
VERMELHO = "C0392B"

AVISO_FONTE = (
    "Os dados deste relatório refletem a última consulta registrada no sistema, com a origem e a "
    "data indicadas em cada linha. Ausência de informação não equivale a ausência de pendência."
)


def _agora() -> datetime:
    return datetime.now(UTC)


def _fmt_dt(valor: datetime | None) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else "—"


def _fmt_d(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


_ROTULOS = {
    "TRANSMITIDA": "Transmitida", "EM_PROCESSAMENTO": "Em processamento",
    "EM_ANALISE": "Em análise", "HOMOLOGADA": "Homologada",
    "NAO_HOMOLOGADA": "Não homologada", "HOMOLOGADA_PARCIALMENTE": "Homologada parcialmente",
    "CANCELADA": "Cancelada", "COM_EXIGENCIA": "Com exigência/intimação",
    "SEM_INFORMACAO": "Sem informação atualizada",
    "ATIVA": "Ativa", "PROXIMA_VENCIMENTO": "Próxima do vencimento", "EXPIRADA": "Expirada",
    "REVOGADA": "Revogada", "DESCONHECIDA": "Desconhecida",
    "REGULAR": "Sem pendências", "COM_PENDENCIAS": "Com pendências",
    "NAO_CONSULTADO": "Não consultado", "INDISPONIVEL": "Indisponível",
    "NAO_AUTORIZADO": "Não autorizado", "SEM_DADOS": "Sem dados", "OK": "OK",
    "DEBITO_FEDERAL": "Débito federal", "DEBITO_PREVIDENCIARIO": "Débito previdenciário",
    "DEBITO_EM_COBRANCA": "Débito em cobrança", "DEBITO_SUSPENSO": "Débito suspenso",
    "PARCELAMENTO": "Parcelamento", "OBRIGACAO_ACESSORIA": "Obrigação acessória",
    "PENDENCIA_PAGAMENTO": "Pendência de pagamento", "OUTROS": "Outros",
    "SIMULADOR": "Simulador (teste)", "PLANILHA": "Planilha", "MANUAL": "Manual",
    "IMPORTACAO_RELATORIO": "Relatório importado",
    "API_INTEGRA_CONTADOR": "API Integra Contador",
    "VERDE": "Verde", "AMARELO": "Amarelo", "VERMELHO": "Vermelho", "CINZA": "Cinza",
    "CRITICA": "Crítica", "ALTA": "Alta", "MEDIA": "Média", "BAIXA": "Baixa", "INFO": "Informativa",
}


def _rot(valor: Any) -> str:
    """Rótulo legível para códigos internos (usado nos relatórios em PDF)."""
    texto = str(valor or "")
    return _ROTULOS.get(texto, texto.replace("_", " ").capitalize() if texto else "—")


def _num(valor: Any) -> float:
    try:
        return float(Decimal(str(valor or 0)))
    except Exception:  # noqa: BLE001
        return 0.0


# --------------------------------------------------------------------- Excel
def _aba(wb: Workbook, titulo: str, cabecalhos: list[str], larguras: list[int] | None = None):
    ws = wb.create_sheet(titulo) if wb.sheetnames != ["Sheet"] else wb.active
    ws.title = titulo
    for idx, nome in enumerate(cabecalhos, start=1):
        celula = ws.cell(row=1, column=idx, value=nome)
        celula.font = Font(bold=True, color="FFFFFF", size=10)
        celula.fill = PatternFill("solid", fgColor=AZUL_MARINHO)
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        largura = (larguras[idx - 1] if larguras and idx <= len(larguras) else 0)
        ws.column_dimensions[get_column_letter(idx)].width = largura or max(14, len(nome) + 4)
    ws.freeze_panes = "A2"
    return ws


def _aba_procedencia(wb: Workbook, contexto: dict[str, Any]) -> None:
    ws = wb.create_sheet("Procedência")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 96
    linhas = [
        ("Relatório", contexto.get("titulo", "")),
        ("Gerado em", _fmt_dt(_agora()) + " (UTC)"),
        ("Gerado por", contexto.get("usuario", "")),
        ("Organização", contexto.get("organizacao", "")),
        ("Filtros aplicados", contexto.get("filtros", "nenhum")),
        ("Fonte — procurações", settings.connector_procuracao),
        ("Fonte — PER/DCOMP", settings.connector_compensacao),
        ("Fonte — situação fiscal", settings.connector_situacao_fiscal),
        ("", ""),
        ("Aviso", AVISO_FONTE),
        ("Ressalva de causalidade", RESSALVA_PADRAO),
        ("Transmissão x homologação",
         "Declaração transmitida não equivale a compensação homologada."),
        ("Procurações",
         "A situação só é considerada válida quando confirmada por fonte autorizada; "
         "caso contrário consta como DESCONHECIDA (semáforo cinza)."),
    ]
    if "simulador" in {settings.connector_procuracao, settings.connector_compensacao,
                       settings.connector_situacao_fiscal}:
        linhas.append(("ATENÇÃO",
                       "Há fonte em modo SIMULADOR: os dados correspondentes são fictícios e "
                       "não provêm da Receita Federal."))
    for i, (chave, valor) in enumerate(linhas, start=1):
        c1 = ws.cell(row=i, column=1, value=chave)
        c1.font = Font(bold=True, size=10)
        c1.fill = PatternFill("solid", fgColor=CINZA)
        c2 = ws.cell(row=i, column=2, value=valor)
        c2.alignment = Alignment(wrap_text=True, vertical="top")


def _salvar(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def carteira_excel(
    db: Session, organizacao_id: str, *, contexto: dict[str, Any],
    responsavel: str | None = None,
) -> bytes:
    """Posição consolidada: clientes, procurações, PER/DCOMP e situação fiscal."""
    consulta = select(Cliente).where(Cliente.organizacao_id == organizacao_id)
    if responsavel:
        consulta = consulta.where(Cliente.responsavel == responsavel)
    clientes = list(db.scalars(consulta.order_by(Cliente.razao_social)))
    ids = [c.id for c in clientes]

    wb = Workbook()

    ws = _aba(wb, "Clientes",
              ["CNPJ", "Razão social", "Nome fantasia", "Responsável", "Tributos",
               "Situação fiscal", "Total de débitos", "Pendências", "Última consulta fiscal",
               "Origem", "Ativo"],
              [20, 42, 28, 20, 22, 20, 18, 12, 20, 18, 8])
    for cliente in clientes:
        snap = db.scalars(
            select(SituacaoFiscalSnapshot)
            .where(SituacaoFiscalSnapshot.cliente_id == cliente.id)
            .order_by(SituacaoFiscalSnapshot.consultado_em.desc()).limit(1)
        ).first()
        ws.append([
            formatar_cnpj(cliente.cnpj), cliente.razao_social, cliente.nome_fantasia or "",
            cliente.responsavel or "", cliente.tributos_trabalhados or "",
            snap.situacao_geral if snap else "NAO_CONSULTADO",
            _num(snap.total_debitos) if snap else 0,
            snap.qtd_pendencias if snap else 0,
            _fmt_dt(snap.consultado_em) if snap else "nunca",
            snap.origem if snap else "—",
            "Sim" if cliente.ativo else "Não",
        ])
    for linha in ws.iter_rows(min_row=2, min_col=7, max_col=7):
        for celula in linha:
            celula.number_format = '#,##0.00'

    ws = _aba(wb, "Procurações",
              ["CNPJ", "Cliente", "Número", "Procurador", "Início", "Validade",
               "Dias p/ vencer", "Situação (sistema)", "Declarada", "Semáforo",
               "Validada por fonte", "Disponibilidade", "Última consulta"],
              [20, 36, 20, 18, 12, 12, 14, 20, 18, 12, 16, 18, 20])
    procuracoes = db.scalars(
        select(Procuracao).where(Procuracao.cliente_id.in_(ids))
    ).all() if ids else []
    mapa_clientes = {c.id: c for c in clientes}
    for proc in procuracoes:
        cliente = mapa_clientes[proc.cliente_id]
        ws.append([
            formatar_cnpj(cliente.cnpj), cliente.razao_social, proc.numero or "",
            proc.procurador_doc or "", _fmt_d(proc.data_inicio), _fmt_d(proc.data_fim),
            dias_para_vencer(proc) if proc.data_fim else "—",
            proc.situacao, proc.situacao_declarada, str(semaforo(proc)),
            "Sim" if proc.validada_por_fonte else "Não",
            proc.disponibilidade, _fmt_dt(proc.consultado_em),
        ])

    ws = _aba(wb, "PER-DCOMP",
              ["CNPJ", "Cliente", "PER/DCOMP", "Tributo", "Período", "Transmissão",
               "Débito", "Crédito", "Compensado", "Não homologado", "Situação",
               "Despacho", "Intimação", "Origem", "Disponibilidade", "Última consulta"],
              [20, 34, 30, 14, 12, 14, 14, 14, 14, 16, 22, 16, 12, 18, 18, 20])
    compensacoes = db.scalars(
        select(Compensacao).where(Compensacao.cliente_id.in_(ids))
    ).all() if ids else []
    for comp in compensacoes:
        cliente = mapa_clientes[comp.cliente_id]
        ws.append([
            formatar_cnpj(cliente.cnpj), cliente.razao_social, comp.numero_perdcomp,
            comp.tributo or "", comp.periodo_apuracao or "", _fmt_d(comp.data_transmissao),
            _num(comp.valor_debito), _num(comp.valor_credito), _num(comp.valor_compensado),
            _num(comp.valor_nao_homologado), comp.situacao_compensacao,
            comp.numero_despacho or ("Sim" if comp.tem_despacho_decisorio else "—"),
            "Sim" if comp.tem_intimacao else "—",
            comp.origem_informacao, comp.disponibilidade, _fmt_dt(comp.consultado_em),
        ])
    for linha in ws.iter_rows(min_row=2, min_col=7, max_col=10):
        for celula in linha:
            celula.number_format = '#,##0.00'

    ws = _aba(wb, "Situação fiscal",
              ["CNPJ", "Cliente", "Consulta", "Origem", "Disponibilidade", "Situação",
               "Total exigível", "Previdenciário", "Federal", "Em cobrança", "Suspenso",
               "Parcelado", "Pendências"],
              [20, 34, 20, 18, 18, 18, 16, 16, 16, 16, 14, 14, 12])
    for cliente in clientes:
        for snap in db.scalars(
            select(SituacaoFiscalSnapshot)
            .where(SituacaoFiscalSnapshot.cliente_id == cliente.id)
            .order_by(SituacaoFiscalSnapshot.consultado_em.desc()).limit(10)
        ):
            ws.append([
                formatar_cnpj(cliente.cnpj), cliente.razao_social, _fmt_dt(snap.consultado_em),
                snap.origem, snap.disponibilidade, snap.situacao_geral,
                _num(snap.total_debitos), _num(snap.total_previdenciario),
                _num(snap.total_federal), _num(snap.total_em_cobranca),
                _num(snap.total_suspenso), _num(snap.total_parcelado), snap.qtd_pendencias,
            ])
    for linha in ws.iter_rows(min_row=2, min_col=7, max_col=12):
        for celula in linha:
            celula.number_format = '#,##0.00'

    _aba_procedencia(wb, {**contexto, "titulo": "Carteira consolidada"})
    return _salvar(wb)


def alertas_excel(
    db: Session, organizacao_id: str, *, contexto: dict[str, Any],
    desde: datetime | None = None, status: str | None = None,
) -> bytes:
    consulta = select(Alerta).where(Alerta.organizacao_id == organizacao_id)
    if desde:
        consulta = consulta.where(Alerta.gerado_em >= desde)
    if status:
        consulta = consulta.where(Alerta.status == status)
    alertas = list(db.scalars(consulta.order_by(Alerta.gerado_em.desc())))

    wb = Workbook()
    ws = _aba(wb, "Alertas",
              ["Gerado em", "Criticidade", "Tipo", "CNPJ", "Cliente", "Título", "Mensagem",
               "Por que foi gerado", "Fonte", "Consulta da evidência", "Status",
               "Tratado por", "Tratado em", "Nota"],
              [18, 14, 28, 20, 32, 40, 60, 70, 18, 20, 14, 24, 18, 40])
    for alerta in alertas:
        cliente = db.get(Cliente, alerta.cliente_id) if alerta.cliente_id else None
        evidencia = (alerta.evidencias or [{}])[0]
        ws.append([
            _fmt_dt(alerta.gerado_em), alerta.criticidade, alerta.tipo,
            formatar_cnpj(cliente.cnpj) if cliente else "", cliente.razao_social if cliente else "",
            alerta.titulo, alerta.mensagem, alerta.explicacao or "",
            str(evidencia.get("fonte", "")), str(evidencia.get("consultado_em", "")),
            alerta.status, alerta.resolvido_por or "", _fmt_dt(alerta.resolvido_em),
            alerta.nota_resolucao or "",
        ])
    for linha in ws.iter_rows(min_row=2):
        for celula in linha:
            celula.alignment = Alignment(vertical="top", wrap_text=True)

    _aba_procedencia(wb, {**contexto, "titulo": "Relação de alertas"})
    return _salvar(wb)


def extrato_consultas_excel(
    db: Session, organizacao_id: str, *, contexto: dict[str, Any],
    cliente_id: str | None = None, dias: int = 90,
) -> bytes:
    """Extrato de todas as consultas feitas — para prestação de contas ao cliente."""
    inicio = _agora() - timedelta(days=dias)
    consulta_clientes = select(Cliente).where(Cliente.organizacao_id == organizacao_id)
    if cliente_id:
        consulta_clientes = consulta_clientes.where(Cliente.id == cliente_id)
    clientes = {c.id: c for c in db.scalars(consulta_clientes)}

    linhas: list[list[Any]] = []
    for snap in db.scalars(
        select(SituacaoFiscalSnapshot).where(
            SituacaoFiscalSnapshot.organizacao_id == organizacao_id,
            SituacaoFiscalSnapshot.consultado_em >= inicio,
        )
    ):
        cliente = clientes.get(snap.cliente_id)
        if cliente is None:
            continue
        linhas.append([_fmt_dt(snap.consultado_em), "Situação fiscal",
                       formatar_cnpj(cliente.cnpj), cliente.razao_social, "—",
                       snap.origem, snap.disponibilidade, snap.situacao_geral,
                       _num(snap.total_debitos), snap.criado_por or "sistema"])

    for consulta in db.scalars(
        select(ProcuracaoConsulta).where(ProcuracaoConsulta.consultado_em >= inicio)
    ):
        proc = db.get(Procuracao, consulta.procuracao_id)
        cliente = clientes.get(proc.cliente_id) if proc else None
        if cliente is None:
            continue
        linhas.append([_fmt_dt(consulta.consultado_em), "Procuração",
                       formatar_cnpj(cliente.cnpj), cliente.razao_social, proc.numero or "",
                       consulta.origem, consulta.disponibilidade,
                       consulta.situacao_retornada or "—", 0, consulta.criado_por or "sistema"])

    for evento in db.scalars(
        select(CompensacaoEvento).where(CompensacaoEvento.registrado_em >= inicio)
    ):
        comp = db.get(Compensacao, evento.compensacao_id)
        cliente = clientes.get(comp.cliente_id) if comp else None
        if cliente is None:
            continue
        linhas.append([_fmt_dt(evento.registrado_em), f"PER/DCOMP — {evento.tipo}",
                       formatar_cnpj(cliente.cnpj), cliente.razao_social, comp.numero_perdcomp,
                       evento.origem, evento.disponibilidade or "—",
                       evento.situacao_nova or "—", 0, evento.criado_por or "sistema"])

    linhas.sort(key=lambda x: x[0], reverse=True)

    wb = Workbook()
    ws = _aba(wb, "Extrato de consultas",
              ["Quando", "Tipo", "CNPJ", "Cliente", "Documento", "Fonte",
               "Disponibilidade", "Resultado", "Valor apurado", "Executado por"],
              [18, 26, 20, 34, 30, 20, 18, 24, 16, 26])
    for linha in linhas:
        ws.append(linha)
    for linha in ws.iter_rows(min_row=2, min_col=9, max_col=9):
        for celula in linha:
            celula.number_format = '#,##0.00'

    _aba_procedencia(wb, {**contexto, "titulo": f"Extrato de consultas ({dias} dias)"})
    return _salvar(wb)


# ----------------------------------------------------------------------- PDF
def cliente_pdf(db: Session, cliente: Cliente, *, contexto: dict[str, Any]) -> bytes:
    """Posição completa de um cliente, pronta para enviar ao responsável."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    marinho = colors.HexColor("#1B2A4A")
    cinza_claro = colors.HexColor("#F2F4F8")
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=estilos["Title"], fontSize=17,
                            textColor=marinho, alignment=0, spaceAfter=2)
    subtitulo = ParagraphStyle("subtitulo", parent=estilos["Normal"], fontSize=9,
                               textColor=colors.HexColor("#6B7686"), spaceAfter=10)
    secao = ParagraphStyle("secao", parent=estilos["Heading2"], fontSize=11.5,
                           textColor=marinho, spaceBefore=12, spaceAfter=5)
    corpo = ParagraphStyle("corpo", parent=estilos["Normal"], fontSize=8.6, leading=12)
    nota = ParagraphStyle("nota", parent=estilos["Normal"], fontSize=7.6, leading=10.5,
                          textColor=colors.HexColor("#6B7686"), alignment=TA_JUSTIFY)
    celula = ParagraphStyle("celula", parent=estilos["Normal"], fontSize=7.6, leading=9.8)

    def tabela(cabecalho: list[str], linhas: list[list[Any]], larguras: list[float]):
        dados = [[Paragraph(f"<b>{c}</b>", celula) for c in cabecalho]]
        for linha in linhas:
            dados.append([Paragraph(str(v), celula) for v in linha])
        t = Table(dados, colWidths=larguras, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), marinho),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DFE4EC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, cinza_claro]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title=f"Monitor Tributário — {cliente.razao_social}",
        author="Monitor Tributário",
    )
    conteudo: list[Any] = []

    conteudo.append(Paragraph("Posição tributária do cliente", titulo))
    conteudo.append(Paragraph(
        f"{cliente.razao_social} &nbsp;·&nbsp; CNPJ {formatar_cnpj(cliente.cnpj)}"
        f"{' &nbsp;·&nbsp; ' + cliente.responsavel if cliente.responsavel else ''}"
        f"<br/>Emitido em {_fmt_dt(_agora())} (UTC) por {contexto.get('usuario', '')}", subtitulo))

    # --- Procurações ---
    conteudo.append(Paragraph("Procurações eletrônicas", secao))
    procuracoes = list(db.scalars(select(Procuracao).where(Procuracao.cliente_id == cliente.id)))
    if not procuracoes:
        conteudo.append(Paragraph("Nenhuma procuração cadastrada.", corpo))
    else:
        linhas = [[
            p.numero or "—", _fmt_d(p.data_fim),
            f"{dias_para_vencer(p)} dia(s)" if p.data_fim else "—",
            _rot(p.situacao), _rot(str(semaforo(p))),
            "Sim" if p.validada_por_fonte else "Não",
            _fmt_dt(p.consultado_em),
        ] for p in procuracoes]
        conteudo.append(tabela(
            ["Número", "Validade", "Prazo", "Situação", "Semáforo", "Validada", "Consulta"],
            linhas, [78, 55, 48, 72, 48, 44, 78]))
        conteudo.append(Spacer(1, 4))
        conteudo.append(Paragraph(
            "A situação só é considerada confirmada quando validada por fonte autorizada; "
            "caso contrário o semáforo permanece cinza e a situação, desconhecida.", nota))

    # --- PER/DCOMP ---
    conteudo.append(Paragraph("Compensações (PER/DCOMP)", secao))
    compensacoes = list(db.scalars(select(Compensacao).where(Compensacao.cliente_id == cliente.id)))
    if not compensacoes:
        conteudo.append(Paragraph("Nenhuma PER/DCOMP cadastrada.", corpo))
    else:
        linhas = [[
            c.numero_perdcomp, c.tributo or "—", c.periodo_apuracao or "—",
            f"{_num(c.valor_credito):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            _rot(c.situacao_compensacao),
            (c.numero_despacho or ("Sim" if c.tem_despacho_decisorio else "—")),
            "Sim" if c.tem_intimacao else "—",
            _fmt_dt(c.consultado_em),
        ] for c in compensacoes]
        conteudo.append(tabela(
            ["PER/DCOMP", "Tributo", "Período", "Crédito (R$)", "Situação",
             "Despacho", "Intim.", "Consulta"],
            linhas, [104, 44, 40, 56, 86, 52, 30, 76]))
        conteudo.append(Spacer(1, 4))
        conteudo.append(Paragraph(
            "Declaração transmitida não equivale a compensação homologada. Situações marcadas "
            "como “sem informação atualizada” indicam ausência de retorno da fonte, não "
            "deferimento.", nota))

    # --- Situação fiscal ---
    conteudo.append(Paragraph("Situação fiscal", secao))
    snapshots = list(db.scalars(
        select(SituacaoFiscalSnapshot)
        .where(SituacaoFiscalSnapshot.cliente_id == cliente.id)
        .order_by(SituacaoFiscalSnapshot.consultado_em.desc()).limit(6)
    ))
    if not snapshots:
        conteudo.append(Paragraph("Nenhuma consulta de situação fiscal registrada.", corpo))
    else:
        atual = snapshots[0]
        linhas = [[
            _fmt_dt(s.consultado_em), _rot(s.origem), _rot(s.disponibilidade),
            _rot(s.situacao_geral),
            f"{_num(s.total_debitos):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            s.qtd_pendencias,
        ] for s in snapshots]
        conteudo.append(tabela(
            ["Consulta", "Fonte", "Disponibilidade", "Situação", "Total exigível (R$)", "Pend."],
            linhas, [78, 72, 72, 86, 86, 36]))

        if atual.pendencias:
            conteudo.append(Spacer(1, 8))
            conteudo.append(Paragraph(
                f"Pendências na consulta de {_fmt_dt(atual.consultado_em)}", secao))
            det = [[
                _rot(p.get("categoria")), p.get("codigo") or "—", p.get("descricao", ""),
                p.get("periodo") or "—",
                f"{_num(p.get('valor')):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                p.get("situacao") or "—",
            ] for p in atual.pendencias]
            conteudo.append(tabela(
                ["Categoria", "Código", "Descrição", "Período", "Valor (R$)", "Situação"],
                det, [96, 60, 146, 44, 62, 60]))

    # --- Comparativo ---
    comparativo = db.scalars(
        select(SituacaoFiscalComparativo)
        .where(SituacaoFiscalComparativo.cliente_id == cliente.id)
        .order_by(SituacaoFiscalComparativo.created_at.desc()).limit(1)
    ).first()
    if comparativo:
        conteudo.append(Paragraph("Comparativo entre as duas últimas consultas", secao))
        def brl(v: Any) -> str:
            return f"{_num(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        conteudo.append(tabela(
            ["Anterior (R$)", "Atual (R$)", "Variação (R$)", "Novos", "Baixados",
             "Remanescentes", "Alterados"],
            [[brl(comparativo.total_anterior), brl(comparativo.total_atual),
              brl(comparativo.diferenca), len(comparativo.novos or []),
              len(comparativo.baixados or []), len(comparativo.permanecem or []),
              len(comparativo.alterados or [])]],
            [72, 72, 72, 44, 52, 72, 52]))
        conteudo.append(Spacer(1, 4))
        conteudo.append(Paragraph(comparativo.ressalva or RESSALVA_PADRAO, nota))

    # --- Alertas ---
    conteudo.append(Paragraph("Alertas em aberto", secao))
    alertas = list(db.scalars(
        select(Alerta).where(
            Alerta.cliente_id == cliente.id,
            Alerta.status.in_([StatusAlerta.NOVO, StatusAlerta.EM_ANALISE]),
        ).order_by(Alerta.gerado_em.desc()).limit(20)
    ))
    if not alertas:
        conteudo.append(Paragraph("Nenhum alerta em aberto.", corpo))
    else:
        linhas = [[_rot(a.criticidade), a.titulo, a.mensagem, _fmt_dt(a.gerado_em)]
                  for a in alertas]
        conteudo.append(tabela(["Criticidade", "Alerta", "Descrição", "Gerado em"],
                               linhas, [54, 130, 220, 64]))

    # --- Rodapé de procedência ---
    rodape = [
        Paragraph("Procedência e limites", secao),
        Paragraph(AVISO_FONTE, nota),
        Spacer(1, 3),
        Paragraph(
            f"Fontes configuradas — procurações: <b>{settings.connector_procuracao}</b>; "
            f"PER/DCOMP: <b>{settings.connector_compensacao}</b>; "
            f"situação fiscal: <b>{settings.connector_situacao_fiscal}</b>.", nota),
        Spacer(1, 3),
        Paragraph(
            "Este documento é gerado automaticamente a partir das consultas registradas e "
            "<b>não constitui parecer jurídico ou contábil</b>. As conclusões exigem conferência "
            "humana antes de qualquer providência junto ao contribuinte ou à Receita Federal.",
            nota),
    ]
    if "simulador" in {settings.connector_procuracao, settings.connector_compensacao,
                       settings.connector_situacao_fiscal}:
        rodape.append(Spacer(1, 3))
        rodape.append(Paragraph(
            "<b>ATENÇÃO:</b> há fonte em modo SIMULADOR — os dados correspondentes são "
            "fictícios e não provêm da Receita Federal.", nota))
    conteudo.append(KeepTogether(rodape))

    def numerar(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#6B7686"))
        canvas.drawString(16 * mm, 10 * mm, "Monitor Tributário — documento interno")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Página {documento.page}")
        canvas.setStrokeColor(colors.HexColor("#DFE4EC"))
        canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
        canvas.restoreState()

    doc.build(conteudo, onFirstPage=numerar, onLaterPages=numerar)
    return buffer.getvalue()
