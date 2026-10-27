"""Clientes: quem compra, KYC e histórico."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Cliente
from ...security import flash
from ...services import clientes as svc_clientes, notificacoes
from ..render import render

router = APIRouter(prefix="/clientes")


@router.get("")
def lista(request: Request, q: str = "", db: Session = Depends(get_db)):
    clientes = svc_clientes.listar(db, q)
    linhas = [{"cliente": c, **svc_clientes.resumo_cliente(db, c)} for c in clientes]
    return render(request, "admin/clientes.html", db, linhas=linhas, q=q)


@router.get("/{cliente_id}")
def detalhe(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        return RedirectResponse("/admin/clientes", status_code=303)
    return render(
        request, "admin/cliente.html", db, cliente=cliente, resumo=svc_clientes.resumo_cliente(db, cliente),
        whatsapp=notificacoes.link_whatsapp(cliente.telefone, f"Oi, {cliente.nome.split(' ')[0]}! "),
    )


@router.post("/{cliente_id}/observacoes")
async def observacoes(request: Request, cliente_id: int, observacoes: str = Form(""), aceita_marketing: str = Form(""), db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    cliente.observacoes = observacoes.strip()
    cliente.aceita_marketing = aceita_marketing == "1"
    db.commit()
    flash(request, "Anotações salvas.")
    return RedirectResponse(f"/admin/clientes/{cliente_id}", status_code=303)
