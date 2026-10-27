"""Livro-caixa: toda entrada e saída de dinheiro passa por aqui."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import LancamentoCaixa
from ..utils import hoje


def lancar(
    db: Session,
    tipo: str,
    categoria: str,
    valor_cents: int,
    descricao: str,
    ref_tipo: str = "",
    ref_id: int | None = None,
    data: date | None = None,
) -> LancamentoCaixa:
    assert tipo in {"entrada", "saida"}
    lanc = LancamentoCaixa(
        data=data or hoje(),
        tipo=tipo,
        categoria=categoria,
        valor_cents=abs(int(valor_cents)),
        descricao=descricao[:200],
        ref_tipo=ref_tipo,
        ref_id=ref_id,
    )
    db.add(lanc)
    db.flush()
    return lanc


def saldo(db: Session, ate: date | None = None) -> int:
    q = select(
        func.coalesce(func.sum(LancamentoCaixa.valor_cents).filter(LancamentoCaixa.tipo == "entrada"), 0)
        - func.coalesce(func.sum(LancamentoCaixa.valor_cents).filter(LancamentoCaixa.tipo == "saida"), 0)
    )
    if ate:
        q = q.where(LancamentoCaixa.data <= ate)
    return int(db.execute(q).scalar() or 0)


def extrato(db: Session, inicio: date, fim: date) -> list[LancamentoCaixa]:
    return list(
        db.execute(
            select(LancamentoCaixa)
            .where(LancamentoCaixa.data >= inicio, LancamentoCaixa.data <= fim)
            .order_by(LancamentoCaixa.data.desc(), LancamentoCaixa.id.desc())
        ).scalars()
    )


def resumo(db: Session, inicio: date, fim: date) -> dict:
    linhas = db.execute(
        select(LancamentoCaixa.tipo, LancamentoCaixa.categoria, func.sum(LancamentoCaixa.valor_cents))
        .where(LancamentoCaixa.data >= inicio, LancamentoCaixa.data <= fim)
        .group_by(LancamentoCaixa.tipo, LancamentoCaixa.categoria)
    ).all()
    entradas: dict[str, int] = {}
    saidas: dict[str, int] = {}
    for tipo, categoria, total in linhas:
        (entradas if tipo == "entrada" else saidas)[categoria] = int(total or 0)
    total_entradas = sum(entradas.values())
    total_saidas = sum(saidas.values())
    return {
        "entradas": entradas,
        "saidas": saidas,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "resultado": total_entradas - total_saidas,
        "saldo_inicial": saldo(db, inicio) - _movimento_no_dia_inicial(db, inicio),
        "saldo_final": saldo(db, fim),
    }


def _movimento_no_dia_inicial(db: Session, dia: date) -> int:
    q = select(
        func.coalesce(func.sum(LancamentoCaixa.valor_cents).filter(LancamentoCaixa.tipo == "entrada"), 0)
        - func.coalesce(func.sum(LancamentoCaixa.valor_cents).filter(LancamentoCaixa.tipo == "saida"), 0)
    ).where(LancamentoCaixa.data == dia)
    return int(db.execute(q).scalar() or 0)


def por_dia(db: Session, inicio: date, fim: date) -> dict[date, dict[str, int]]:
    linhas = db.execute(
        select(LancamentoCaixa.data, LancamentoCaixa.tipo, func.sum(LancamentoCaixa.valor_cents))
        .where(LancamentoCaixa.data >= inicio, LancamentoCaixa.data <= fim)
        .group_by(LancamentoCaixa.data, LancamentoCaixa.tipo)
    ).all()
    resultado: dict[date, dict[str, int]] = {}
    for dia, tipo, total in linhas:
        resultado.setdefault(dia, {"entrada": 0, "saida": 0})[tipo] = int(total or 0)
    return resultado
