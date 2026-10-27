"""Compras e fornecedores."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Compra, Fornecedor, Produto
from ...security import flash
from ...services import catalogo, compras as svc_compras, estoque
from ...utils import parse_dinheiro
from ..render import render

router = APIRouter()


@router.get("/compras")
def lista(request: Request, status: str = "", db: Session = Depends(get_db)):
    return render(request, "admin/compras.html", db, compras=svc_compras.listar(db, status or None), status=status, repor=estoque.para_repor(db), fornecedores=svc_compras.fornecedores(db))


@router.post("/compras/nova")
async def nova(request: Request, fornecedor_id: str = Form(""), db: Session = Depends(get_db)):
    compra = svc_compras.criar(db, int(fornecedor_id) if fornecedor_id else None)
    db.commit()
    return RedirectResponse(f"/admin/compras/{compra.id}", status_code=303)


@router.post("/compras/sugerir")
async def sugerir(request: Request, db: Session = Depends(get_db)):
    compras = svc_compras.criar_sugeridas(db)
    db.commit()
    if not compras:
        flash(request, "Nada para repor agora.", "aviso")
        return RedirectResponse("/admin/compras", status_code=303)
    flash(request, f"{len(compras)} compra(s) sugerida(s) criada(s) como rascunho. Revise as quantidades e envie ao fornecedor.")
    return RedirectResponse(f"/admin/compras/{compras[0].id}" if len(compras) == 1 else "/admin/compras", status_code=303)


@router.get("/compras/{compra_id}")
def detalhe(request: Request, compra_id: int, db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    return render(request, "admin/compra.html", db, compra=compra, produtos=catalogo.produtos(db, somente_ativos=False), fornecedores=svc_compras.fornecedores(db))


@router.post("/compras/{compra_id}/itens")
async def adicionar_item(request: Request, compra_id: int, produto_id: int = Form(...), quantidade: int = Form(1), custo: str = Form(""), db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    produto = db.get(Produto, produto_id)
    try:
        svc_compras.adicionar_item(db, compra, produto, quantidade, parse_dinheiro(custo) if custo else None)
        db.commit()
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(f"/admin/compras/{compra_id}", status_code=303)


@router.post("/compras/{compra_id}/itens/{item_id}/remover")
async def remover_item(request: Request, compra_id: int, item_id: int, db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    svc_compras.remover_item(db, compra, item_id)
    db.commit()
    return RedirectResponse(f"/admin/compras/{compra_id}", status_code=303)


@router.post("/compras/{compra_id}/fornecedor")
async def definir_fornecedor(request: Request, compra_id: int, fornecedor_id: str = Form(""), observacoes: str = Form(""), db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    compra.fornecedor_id = int(fornecedor_id) if fornecedor_id else None
    compra.observacoes = observacoes.strip()
    db.commit()
    return RedirectResponse(f"/admin/compras/{compra_id}", status_code=303)


@router.post("/compras/{compra_id}/enviar")
async def enviar(request: Request, compra_id: int, db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    try:
        svc_compras.enviar(db, compra)
        db.commit()
        flash(request, f"Compra {compra.numero} marcada como enviada ao fornecedor.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(f"/admin/compras/{compra_id}", status_code=303)


@router.post("/compras/{compra_id}/receber")
async def receber(request: Request, compra_id: int, db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    form = await request.form()
    quantidades = {}
    for chave, valor in form.multi_items():
        if chave.startswith("recebido_") and valor != "":
            quantidades[int(chave[9:])] = int(valor)
    frete = parse_dinheiro(form.get("frete") or "") if form.get("frete") else None
    try:
        svc_compras.receber(db, compra, quantidades or None, frete)
        if form.get("pagar"):
            svc_compras.pagar(db, compra)
        db.commit()
        flash(request, f"Compra {compra.numero} recebida: estoque atualizado e custo médio recalculado.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(f"/admin/compras/{compra_id}", status_code=303)


@router.post("/compras/{compra_id}/pagar")
async def pagar(request: Request, compra_id: int, db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    svc_compras.pagar(db, compra)
    db.commit()
    flash(request, f"Compra {compra.numero} paga: saída registrada no caixa.")
    return RedirectResponse(request.headers.get("referer") or f"/admin/compras/{compra_id}", status_code=303)


@router.post("/compras/{compra_id}/cancelar")
async def cancelar(request: Request, compra_id: int, db: Session = Depends(get_db)):
    compra = db.get(Compra, compra_id)
    try:
        svc_compras.cancelar(db, compra)
        db.commit()
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(f"/admin/compras/{compra_id}", status_code=303)


# ------------------------------------------------------------ fornecedores
@router.get("/fornecedores")
def fornecedores(request: Request, db: Session = Depends(get_db)):
    todos = db.query(Fornecedor).order_by(Fornecedor.ativo.desc(), Fornecedor.nome).all()
    return render(request, "admin/fornecedores.html", db, fornecedores=todos)


@router.post("/fornecedores")
async def salvar_fornecedor(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    fid = form.get("id")
    f = db.get(Fornecedor, int(fid)) if fid else Fornecedor(nome="")
    f.nome = (form.get("nome") or "").strip() or "Fornecedor"
    f.contato = (form.get("contato") or "").strip()
    f.telefone = (form.get("telefone") or "").strip()
    f.email = (form.get("email") or "").strip()
    f.prazo_dias = int(form.get("prazo_dias") or 7)
    f.observacoes = (form.get("observacoes") or "").strip()
    f.ativo = form.get("ativo", "1") == "1"
    if not fid:
        db.add(f)
    db.commit()
    flash(request, "Fornecedor salvo.")
    return RedirectResponse("/admin/fornecedores", status_code=303)
