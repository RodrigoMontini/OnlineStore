"""Cadastro de produtos e categorias."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Categoria, Produto, TipoMovimento
from ...security import flash
from ...services import assistente, catalogo, compras as svc_compras, estoque
from ...utils import parse_dinheiro, so_digitos, slugify
from ..render import render

router = APIRouter()


@router.get("/produtos")
def lista(request: Request, q: str = "", db: Session = Depends(get_db)):
    return render(request, "admin/produtos.html", db, produtos=catalogo.produtos(db, busca=q, somente_ativos=False, ordem="nome"), q=q)


@router.get("/produtos/novo")
def novo(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/produto_form.html", db, produto=None, categorias=catalogo.categorias(db, somente_ativas=False), fornecedores=svc_compras.fornecedores(db))


@router.get("/produtos/{produto_id}")
def editar(request: Request, produto_id: int, db: Session = Depends(get_db)):
    produto = db.get(Produto, produto_id)
    if not produto:
        return RedirectResponse("/admin/produtos", status_code=303)
    return render(request, "admin/produto_form.html", db, produto=produto, categorias=catalogo.categorias(db, somente_ativas=False), fornecedores=svc_compras.fornecedores(db), movimentos=estoque.movimentos_recentes(db, 15, produto.id))


@router.post("/produtos/novo")
@router.post("/produtos/{produto_id}")
async def salvar(request: Request, produto_id: int | None = None, db: Session = Depends(get_db)):
    form = await request.form()
    produto = db.get(Produto, produto_id) if produto_id else None
    novo = produto is None
    if novo:
        produto = Produto(sku="", nome="", slug="")
        db.add(produto)
    produto.nome = (form.get("nome") or "").strip() or "Produto sem nome"
    produto.sku = catalogo.sku_unico(db, form.get("sku") or slugify(produto.nome)[:12], produto.id)
    produto.slug = catalogo.slug_unico(db, form.get("slug") or produto.nome, produto.id)
    produto.categoria_id = int(form.get("categoria_id")) if form.get("categoria_id") else None
    produto.fornecedor_id = int(form.get("fornecedor_id")) if form.get("fornecedor_id") else None
    produto.resumo = (form.get("resumo") or "").strip()[:200]
    produto.descricao = (form.get("descricao") or "").strip()
    produto.preco_cents = parse_dinheiro(form.get("preco"))
    produto.custo_cents = parse_dinheiro(form.get("custo"))
    produto.estoque_minimo = int(form.get("estoque_minimo") or 2)
    produto.peso_g = int(so_digitos(form.get("peso_g")) or 200)
    produto.localizacao = (form.get("localizacao") or "").strip()[:40]
    produto.ativo = form.get("ativo") == "1"
    produto.destaque = form.get("destaque") == "1"
    produto.ncm = so_digitos(form.get("ncm"))[:8]
    produto.cest = so_digitos(form.get("cest"))[:7]
    produto.origem = (form.get("origem") or "0")[:1]
    produto.unidade = (form.get("unidade") or "UN").strip().upper()[:6]
    db.flush()
    estoque_inicial = form.get("estoque")
    if estoque_inicial not in (None, ""):
        novo_saldo = int(estoque_inicial)
        if novo_saldo != produto.estoque:
            estoque.movimentar(db, produto, novo_saldo - produto.estoque, TipoMovimento.AJUSTE, observacao="Cadastro" if novo else "Ajuste no cadastro", permitir_negativo=True)
    imagem = form.get("imagem")
    if imagem is not None and getattr(imagem, "filename", ""):
        try:
            produto.imagem = catalogo.salvar_imagem(imagem.filename, await imagem.read())
        except ValueError as exc:
            flash(request, str(exc), "erro")
    db.commit()
    flash(request, f"{produto.nome} salvo.")
    return RedirectResponse(f"/admin/produtos/{produto.id}", status_code=303)


@router.post("/produtos/{produto_id}/descrever")
async def descrever(request: Request, produto_id: int, db: Session = Depends(get_db)):
    corpo = await request.json()
    try:
        resultado = assistente.descrever_produto(corpo.get("nome", ""), corpo.get("categoria", ""), corpo.get("notas", ""))
        return JSONResponse({"ok": True, **resultado})
    except Exception as exc:
        return JSONResponse({"ok": False, "erro": str(exc)}, status_code=400)


# ------------------------------------------------------------- categorias
@router.get("/categorias")
def categorias(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/categorias.html", db, categorias=catalogo.categorias(db, somente_ativas=False))


@router.post("/categorias")
async def salvar_categoria(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    cid = form.get("id")
    c = db.get(Categoria, int(cid)) if cid else Categoria(nome="", slug="")
    c.nome = (form.get("nome") or "").strip() or "Categoria"
    c.slug = slugify(form.get("slug") or c.nome)
    c.descricao = (form.get("descricao") or "").strip()
    c.ordem = int(form.get("ordem") or 0)
    c.ativa = form.get("ativa", "1") == "1"
    if not cid:
        db.add(c)
    db.commit()
    return RedirectResponse("/admin/categorias", status_code=303)
