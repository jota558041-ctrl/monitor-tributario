"""Normalização de valores vindos de planilhas (datas, dinheiro, texto)."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

_EPOCH_EXCEL = date(1899, 12, 30)  # Excel/1900 com o bug do ano bissexto


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_cabecalho(texto: Any) -> str:
    bruto = sem_acento(str(texto or "")).lower().strip()
    bruto = re.sub(r"[^a-z0-9]+", " ", bruto)
    return re.sub(r"\s+", " ", bruto).strip()


def texto_ou_none(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    s = str(valor).strip()
    if s.lower() in {"", "nan", "none", "null", "-", "n/a", "na"}:
        return None
    return s


def parse_data(valor: Any) -> date | None:
    """Aceita date/datetime, serial do Excel e os formatos textuais usuais."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if isinstance(valor, float) and math.isnan(valor):
            return None
        numero = float(valor)
        if 1 <= numero <= 80000:
            return _EPOCH_EXCEL + timedelta(days=int(numero))
        return None
    texto = texto_ou_none(valor)
    if not texto:
        return None
    texto = texto.split("T")[0].split(" ")[0]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(valor: Any) -> Decimal | None:
    """Aceita 1.234,56 / 1,234.56 / R$ 1.234,56 / 1234.56 / número."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, Decimal)):
        return Decimal(str(valor))
    if isinstance(valor, float):
        if math.isnan(valor):
            return None
        return Decimal(str(round(valor, 2)))
    texto = texto_ou_none(valor)
    if not texto:
        return None
    texto = re.sub(r"[rR]\$|\s|[A-Za-z]", "", texto)
    if not texto:
        return None
    negativo = texto.startswith("(") and texto.endswith(")")
    texto = texto.strip("()")
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):      # 1.234,56
            texto = texto.replace(".", "").replace(",", ".")
        else:                                        # 1,234.56
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return -numero if negativo else numero


def parse_bool(valor: Any) -> bool | None:
    texto = texto_ou_none(valor)
    if texto is None:
        return None
    t = sem_acento(texto).lower()
    if t in {"1", "true", "sim", "s", "yes", "y", "verdadeiro"}:
        return True
    if t in {"0", "false", "nao", "n", "no", "falso"}:
        return False
    return None


def parse_periodo(valor: Any) -> str | None:
    """Período de apuração: devolve MM/AAAA, AAAA ou o texto original limpo."""
    d = parse_data(valor)
    if d is not None:
        return f"{d.month:02d}/{d.year}"
    texto = texto_ou_none(valor)
    if not texto:
        return None
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{4})", texto)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    m = re.fullmatch(r"(\d{4})[/\-.](\d{1,2})", texto)
    if m:
        return f"{int(m.group(2)):02d}/{m.group(1)}"
    if re.fullmatch(r"\d{4}", texto):
        return texto
    return texto[:20]
