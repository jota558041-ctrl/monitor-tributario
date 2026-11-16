"""Validação e normalização de CNPJ/CPF (dígitos verificadores - módulo 11)."""
from __future__ import annotations

import re

_SO_DIGITOS = re.compile(r"\D+")


def limpar(doc: str | None) -> str:
    if not doc:
        return ""
    return _SO_DIGITOS.sub("", str(doc))


def _dv(numeros: list[int], pesos: list[int]) -> int:
    soma = sum(n * p for n, p in zip(numeros, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cnpj_valido(doc: str | None) -> bool:
    d = limpar(doc)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    numeros = [int(c) for c in d]
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if _dv(numeros[:12], p1) != numeros[12]:
        return False
    return _dv(numeros[:13], p2) == numeros[13]


def cpf_valido(doc: str | None) -> bool:
    d = limpar(doc)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    numeros = [int(c) for c in d]
    if _dv(numeros[:9], list(range(10, 1, -1))) != numeros[9]:
        return False
    return _dv(numeros[:10], list(range(11, 1, -1))) == numeros[10]


def documento_valido(doc: str | None) -> bool:
    d = limpar(doc)
    if len(d) == 11:
        return cpf_valido(d)
    if len(d) == 14:
        return cnpj_valido(d)
    return False


def formatar_cnpj(doc: str | None) -> str:
    d = limpar(doc)
    if len(d) != 14:
        return d
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def formatar_documento(doc: str | None) -> str:
    d = limpar(doc)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return formatar_cnpj(d)


def gerar_cnpj_valido(base: int) -> str:
    """Gera um CNPJ matematicamente válido a partir de uma base numérica.

    Usado apenas para massa de teste fictícia (nunca para dados reais).
    """
    raiz = f"{base % 100_000_000:08d}" + "0001"
    numeros = [int(c) for c in raiz]
    d1 = _dv(numeros, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = _dv(numeros + [d1], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return raiz + f"{d1}{d2}"
