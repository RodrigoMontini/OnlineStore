"""Posição de estoque, ajustes e histórico de movimentos."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Produto
from ...security import flash
from ...services import estoque as svc_estoque
from ..render import render

router = APIRouter(prefix="/estoque")


@router.get("")
def posicao(request: Request, filtro: str = "", db: Session = Depends(get_db)):
    linhas = svc_estoque.posicao(db, somente_ativos=filtro != "todos")
    if filtro == "repor":
        linhas = [l for l in linhas if l["precisa_repor"]]
    elif filtro == "parados":
        linhas = [l for l in linhas if l["vendidos_30d"] == 0 and l["produto"].estoque > 0]
    return render(
        request, "admin/estoque.html", db, linhas=linhas, filtro=filtro,
        valor_custo=sum(l["valor_custo_cents"] for l in linhas), unidades=sum(l["produto"].estoque for l in linhas),
        repor_total=sum(1 for l in svc_estoque.posicao(db) if l["precisa_repor"]),
    )


@router.post("/{produto_id}/ajustar")
async def ajustar(request: Request, produto_id: int, novo_saldo: int = Form(...), observacao: str = Form("Contagem"), db: Session = Depends(get_db)):
    produto = db.get(Produto, produto_id)
    if not produto:
        flash(request, "Produto não encontrado.", "erro")
        return RedirectResponse("/admin/estoque", status_code=303)
    mov = svc_estoque.ajustar_para(db, produto, novo_saldo, observacao or "Contagem")
    db.commit()
    if mov:
        flash(request, f"{produto.nome}: estoque ajustado para {produto.estoque} ({'+' if mov.quantidade > 0 else ''}{mov.quantidade}).")
    return RedirectResponse(request.headers.get("referer") or "/admin/estoque", status_code=303)


@router.get("/movimentos")
def movimentos(request: Request, produto_id: int | None = None, db: Session = Depends(get_db)):
    produto = db.get(Produto, produto_id) if produto_id else None
    return render(request, "admin/movimentos.html", db, movimentos=svc_estoque.movimentos_recentes(db, 300, produto_id), produto=produto)
