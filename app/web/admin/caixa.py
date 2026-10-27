"""Caixa: extrato, saldo e lançamento manual de despesas."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import LancamentoCaixa
from ...security import flash
from ...services import caixa as svc
from ...utils import parse_dinheiro, periodo
from ..render import render

router = APIRouter(prefix="/caixa")


@router.get("")
def extrato(request: Request, p: str = "mes", inicio: str = "", fim: str = "", db: Session = Depends(get_db)):
    di, df, rotulo = periodo(p, inicio, fim)
    return render(request, "admin/caixa.html", db, lancamentos=svc.extrato(db, di, df), resumo=svc.resumo(db, di, df), saldo=svc.saldo(db), p=p, rotulo=rotulo, inicio=di, fim=df, categorias=LancamentoCaixa.CATEGORIAS)


@router.post("/lancar")
async def lancar(request: Request, tipo: str = Form("saida"), categoria: str = Form("despesa"), valor: str = Form(""), descricao: str = Form(""), data: str = Form(""), db: Session = Depends(get_db)):
    cents = parse_dinheiro(valor)
    if cents <= 0:
        flash(request, "Informe o valor.", "erro")
        return RedirectResponse("/admin/caixa", status_code=303)
    try:
        dia = date.fromisoformat(data) if data else None
    except ValueError:
        dia = None
    svc.lancar(db, tipo if tipo in {"entrada", "saida"} else "saida", categoria, cents, descricao or categoria, ref_tipo="manual", data=dia)
    db.commit()
    flash(request, "Lançamento registrado.")
    return RedirectResponse("/admin/caixa", status_code=303)
