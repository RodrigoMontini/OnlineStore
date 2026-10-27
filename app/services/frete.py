"""Frete: tabela por região (editável no painel) + frete grátis acima de um valor.

Sem contrato com os Correios não há API de preço; a tabela é calibrada com os
preços do balcão e ajustada no painel quando mudarem.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TabelaFrete
from ..utils import NOME_REGIAO, regiao_por_cep, so_digitos, uf_por_cep
from . import configuracoes

TABELA_INICIAL = [
    # metodo, regiao, preco_cents (até 1 kg), prazo_dias
    ("PAC", "SP-capital", 1490, 3), ("SEDEX", "SP-capital", 2290, 1),
    ("PAC", "SP", 1890, 4), ("SEDEX", "SP", 2790, 2),
    ("PAC", "sudeste", 2290, 6), ("SEDEX", "sudeste", 3490, 2),
    ("PAC", "sul", 2490, 7), ("SEDEX", "sul", 3890, 3),
    ("PAC", "centro-oeste", 2690, 8), ("SEDEX", "centro-oeste", 4290, 3),
    ("PAC", "nordeste", 2990, 10), ("SEDEX", "nordeste", 4990, 4),
    ("PAC", "norte", 3490, 12), ("SEDEX", "norte", 5990, 5),
]


def garantir_tabela(db: Session) -> None:
    if db.execute(select(TabelaFrete.id).limit(1)).first():
        return
    for metodo, regiao, preco, prazo in TABELA_INICIAL:
        db.add(TabelaFrete(metodo=metodo, regiao=regiao, preco_cents=preco, prazo_dias=prazo))
    db.flush()


def tabela(db: Session) -> list[TabelaFrete]:
    ordem = list(NOME_REGIAO.keys())
    linhas = list(db.execute(select(TabelaFrete)).scalars())
    return sorted(linhas, key=lambda t: (ordem.index(t.regiao) if t.regiao in ordem else 99, t.metodo))


def cotar(db: Session, cep: str, subtotal_cents: int, peso_g: int = 0) -> dict:
    """Retorna {'ok', 'erro', 'uf', 'regiao', 'opcoes': [{metodo, preco_cents, prazo_dias, gratis}]}"""
    d = so_digitos(cep)
    uf = uf_por_cep(d)
    regiao = regiao_por_cep(d)
    if not uf or not regiao:
        return {"ok": False, "erro": "CEP não encontrado. Confira os 8 dígitos.", "opcoes": []}
    gratis_acima = configuracoes.obter_int(db, "frete_gratis_acima_cents", 0)
    adicional_pct = configuracoes.obter_int(db, "frete_adicional_por_kg_pct", 20)
    processamento = configuracoes.obter_int(db, "frete_dias_adicionais_processamento", 1)
    kg_extra = max(0, math.ceil(max(peso_g, 1) / 1000) - 1)
    opcoes = []
    for linha in db.execute(select(TabelaFrete).where(TabelaFrete.regiao == regiao, TabelaFrete.ativo.is_(True)).order_by(TabelaFrete.preco_cents)).scalars():
        preco = int(round(linha.preco_cents * (1 + adicional_pct / 100.0 * kg_extra)))
        gratis = bool(gratis_acima and subtotal_cents >= gratis_acima and linha.metodo == "PAC")
        opcoes.append(
            {
                "metodo": linha.metodo,
                "preco_cents": 0 if gratis else preco,
                "prazo_dias": linha.prazo_dias + processamento,
                "gratis": gratis,
            }
        )
    if not opcoes:
        return {"ok": False, "erro": "Ainda não entregamos nessa região.", "uf": uf, "regiao": regiao, "opcoes": []}
    return {"ok": True, "uf": uf, "regiao": regiao, "regiao_nome": NOME_REGIAO.get(regiao, regiao), "opcoes": opcoes}


def url_rastreio(codigo: str) -> str:
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return ""
    return f"https://rastreamento.correios.com.br/app/index.php?objetos={codigo}"
