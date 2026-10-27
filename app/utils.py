"""Utilidades: datas no fuso da loja, dinheiro em centavos, CPF/CNPJ, CEP, slugs."""
from __future__ import annotations

import re
import secrets
import string
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import config

FUSO = ZoneInfo(config.FUSO)


# ---------------------------------------------------------------- datas
def agora() -> datetime:
    """Data/hora local da loja, sem tzinfo (o banco guarda tudo no horário local)."""
    return datetime.now(FUSO).replace(tzinfo=None, microsecond=0)


def hoje() -> date:
    return agora().date()


def inicio_do_dia(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def fim_do_dia(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59)


def periodo(nome: str, inicio: str | None = None, fim: str | None = None) -> tuple[date, date, str]:
    """Resolve um período nomeado (hoje, 7d, 30d, mes, mes_anterior, ano, custom)."""
    h = hoje()
    if nome == "hoje":
        return h, h, "Hoje"
    if nome == "ontem":
        o = h - timedelta(days=1)
        return o, o, "Ontem"
    if nome == "7d":
        return h - timedelta(days=6), h, "Últimos 7 dias"
    if nome == "mes":
        return h.replace(day=1), h, "Este mês"
    if nome == "mes_anterior":
        primeiro_deste = h.replace(day=1)
        ultimo_anterior = primeiro_deste - timedelta(days=1)
        return ultimo_anterior.replace(day=1), ultimo_anterior, "Mês anterior"
    if nome == "ano":
        return h.replace(month=1, day=1), h, "Este ano"
    if nome == "custom" and inicio and fim:
        try:
            di = date.fromisoformat(inicio)
            df = date.fromisoformat(fim)
            if di > df:
                di, df = df, di
            return di, df, f"{fmt_data(di)} a {fmt_data(df)}"
        except ValueError:
            pass
    return h - timedelta(days=29), h, "Últimos 30 dias"


def fmt_data(d: date | datetime | None) -> str:
    if not d:
        return "—"
    return d.strftime("%d/%m/%Y")


def fmt_datahora(d: datetime | None) -> str:
    if not d:
        return "—"
    return d.strftime("%d/%m/%Y %H:%M")


def fmt_relativo(d: datetime | None) -> str:
    """'há 3 h', 'há 2 dias' — para filas do painel."""
    if not d:
        return ""
    delta = agora() - d
    segundos = int(delta.total_seconds())
    if segundos < 60:
        return "agora"
    if segundos < 3600:
        return f"há {segundos // 60} min"
    if segundos < 86400:
        return f"há {segundos // 3600} h"
    dias = segundos // 86400
    return f"há {dias} dia" + ("s" if dias > 1 else "")


def idade(nascimento: date | None, em: date | None = None) -> int | None:
    if not nascimento:
        return None
    em = em or hoje()
    anos = em.year - nascimento.year
    if (em.month, em.day) < (nascimento.month, nascimento.day):
        anos -= 1
    return anos


# -------------------------------------------------------------- dinheiro
def brl(centavos: int | None) -> str:
    """1234567 -> 'R$ 12.345,67'."""
    if centavos is None:
        centavos = 0
    negativo = centavos < 0
    centavos = abs(int(centavos))
    reais, cents = divmod(centavos, 100)
    inteiro = f"{reais:,}".replace(",", ".")
    texto = f"R$ {inteiro},{cents:02d}"
    return f"-{texto}" if negativo else texto


def parse_dinheiro(texto: str | int | float | None) -> int:
    """Aceita '12,50', '12.50', 'R$ 1.234,56', 12.5 -> centavos."""
    if texto is None or texto == "":
        return 0
    if isinstance(texto, (int, float)):
        return int(round(float(texto) * 100))
    t = str(texto).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return int(round(float(t) * 100))
    except ValueError:
        return 0


def pct(parte: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return round(100.0 * parte / total, 1)


# ------------------------------------------------------- texto e identidade
def so_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))


def slugify(texto: str) -> str:
    t = sem_acentos(texto).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "item"


def cpf_valido(cpf: str | None) -> bool:
    d = so_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        digito = 0 if digito == 10 else digito
        if digito != int(d[tamanho]):
            return False
    return True


def cnpj_valido(cnpj: str | None) -> bool:
    d = so_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(d[i]) * pesos[i] for i in range(len(pesos)))
        digito = 11 - (soma % 11)
        digito = 0 if digito >= 10 else digito
        if digito != int(d[pos]):
            return False
    return True


def fmt_cpf(cpf: str | None) -> str:
    d = so_digitos(cpf)
    if len(d) != 11:
        return cpf or ""
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def fmt_cnpj(cnpj: str | None) -> str:
    d = so_digitos(cnpj)
    if len(d) != 14:
        return cnpj or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def fmt_cep(cep: str | None) -> str:
    d = so_digitos(cep)
    if len(d) != 8:
        return cep or ""
    return f"{d[:5]}-{d[5:]}"


def fmt_telefone(tel: str | None) -> str:
    d = so_digitos(tel)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return tel or ""


def telefone_whatsapp(tel: str | None) -> str:
    """Número no formato internacional para links wa.me (DDI 55)."""
    d = so_digitos(tel)
    if not d:
        return ""
    if len(d) in (10, 11):
        d = "55" + d
    return d


def email_valido(email: str | None) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (email or "").strip()))


def token_url(tamanho: int = 24) -> str:
    return secrets.token_urlsafe(tamanho)


def codigo_curto(tamanho: int = 6) -> str:
    alfabeto = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


# ----------------------------------------------------------------- CEP/UF
# Faixas de CEP por UF (prefixos de 5 dígitos).
_FAIXAS_UF = [
    ("SP", 1000, 19999), ("RJ", 20000, 28999), ("ES", 29000, 29999), ("MG", 30000, 39999),
    ("BA", 40000, 48999), ("SE", 49000, 49999), ("PE", 50000, 56999), ("AL", 57000, 57999),
    ("PB", 58000, 58999), ("RN", 59000, 59999), ("CE", 60000, 63999), ("PI", 64000, 64999),
    ("MA", 65000, 65999), ("PA", 66000, 68899), ("AP", 68900, 68999), ("AM", 69000, 69299),
    ("RR", 69300, 69399), ("AM", 69400, 69899), ("AC", 69900, 69999), ("DF", 70000, 72799),
    ("GO", 72800, 72999), ("DF", 73000, 73699), ("GO", 73700, 76799), ("RO", 76800, 76999),
    ("TO", 77000, 77999), ("MT", 78000, 78899), ("MS", 79000, 79999), ("PR", 80000, 87999),
    ("SC", 88000, 89999), ("RS", 90000, 99999),
]

REGIAO_UF = {
    "SP": "SP", "RJ": "sudeste", "MG": "sudeste", "ES": "sudeste",
    "PR": "sul", "SC": "sul", "RS": "sul",
    "DF": "centro-oeste", "GO": "centro-oeste", "MT": "centro-oeste", "MS": "centro-oeste",
    "BA": "nordeste", "SE": "nordeste", "AL": "nordeste", "PE": "nordeste", "PB": "nordeste",
    "RN": "nordeste", "CE": "nordeste", "PI": "nordeste", "MA": "nordeste",
    "PA": "norte", "AP": "norte", "AM": "norte", "RR": "norte", "AC": "norte", "RO": "norte", "TO": "norte",
}

NOME_REGIAO = {
    "SP-capital": "São Paulo capital e Grande SP",
    "SP": "Interior de SP",
    "sudeste": "Sudeste (RJ, MG, ES)",
    "sul": "Sul (PR, SC, RS)",
    "centro-oeste": "Centro-Oeste (DF, GO, MT, MS)",
    "nordeste": "Nordeste",
    "norte": "Norte",
}

UFS = sorted({uf for uf, _, _ in _FAIXAS_UF})

# Código IBGE da UF (usado na chave da NF-e).
CODIGO_UF = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17", "MA": "21",
    "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27", "SE": "28", "BA": "29",
    "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41", "SC": "42", "RS": "43", "MS": "50",
    "MT": "51", "GO": "52", "DF": "53",
}


def uf_por_cep(cep: str | None) -> str | None:
    d = so_digitos(cep)
    if len(d) != 8:
        return None
    prefixo = int(d[:5])
    for uf, ini, fim in _FAIXAS_UF:
        if ini <= prefixo <= fim:
            return uf
    return None


def regiao_por_cep(cep: str | None) -> str | None:
    d = so_digitos(cep)
    uf = uf_por_cep(d)
    if not uf:
        return None
    if uf == "SP" and 1000 <= int(d[:5]) <= 9999:
        return "SP-capital"
    return REGIAO_UF[uf]
