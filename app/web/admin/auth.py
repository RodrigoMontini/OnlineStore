"""Login, primeiro acesso (setup) e saída."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Admin
from ...security import flash, hash_senha, verificar_csrf, verificar_senha
from ...services import configuracoes
from ..render import render

router = APIRouter()


def _tem_admin(db: Session) -> bool:
    return db.execute(select(Admin.id).limit(1)).first() is not None


@router.get("/login")
def login(request: Request, next: str = "/admin", db: Session = Depends(get_db)):
    if not _tem_admin(db):
        return RedirectResponse("/admin/setup", status_code=303)
    if request.session.get("admin_id"):
        return RedirectResponse(next or "/admin", status_code=303)
    return render(request, "admin/login.html", db, next=next, erro="")


@router.post("/login", dependencies=[Depends(verificar_csrf)])
async def login_enviar(request: Request, email: str = Form(""), senha: str = Form(""), next: str = Form("/admin"), db: Session = Depends(get_db)):
    admin = db.execute(select(Admin).where(Admin.email == email.strip().lower())).scalar_one_or_none()
    if not admin or not verificar_senha(senha, admin.senha_hash):
        return render(request, "admin/login.html", db, status_code=401, next=next, erro="E-mail ou senha não conferem.")
    request.session["admin_id"] = admin.id
    destino = next if next.startswith("/admin") else "/admin"
    return RedirectResponse(destino, status_code=303)


@router.post("/sair", dependencies=[Depends(verificar_csrf)])
async def sair(request: Request):
    request.session.pop("admin_id", None)
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/setup")
def setup(request: Request, db: Session = Depends(get_db)):
    if _tem_admin(db):
        return RedirectResponse("/admin/login", status_code=303)
    return render(request, "admin/setup.html", db, erros={}, dados={})


@router.post("/setup", dependencies=[Depends(verificar_csrf)])
async def setup_enviar(request: Request, db: Session = Depends(get_db)):
    if _tem_admin(db):
        return RedirectResponse("/admin/login", status_code=303)
    form = await request.form()
    dados = {k: (form.get(k) or "").strip() for k in ("nome", "email", "senha", "senha2", "loja_nome", "pix_chave", "pix_nome", "loja_whatsapp")}
    erros = {}
    if not dados["nome"]:
        erros["nome"] = "Seu nome."
    if "@" not in dados["email"]:
        erros["email"] = "E-mail válido."
    if len(dados["senha"]) < 8:
        erros["senha"] = "Senha com pelo menos 8 caracteres."
    elif dados["senha"] != dados["senha2"]:
        erros["senha2"] = "As senhas não conferem."
    if erros:
        return render(request, "admin/setup.html", db, status_code=400, erros=erros, dados=dados)
    admin = Admin(nome=dados["nome"], email=dados["email"].lower(), senha_hash=hash_senha(dados["senha"]))
    db.add(admin)
    configuracoes.definir_varias(db, {
        "loja_nome": dados["loja_nome"] or configuracoes.PADROES["loja_nome"],
        "pix_chave": dados["pix_chave"],
        "pix_nome": dados["pix_nome"],
        "loja_whatsapp": dados["loja_whatsapp"],
        "setup_concluido": "1",
    })
    db.commit()
    request.session["admin_id"] = admin.id
    flash(request, "Loja pronta. Esta é a sua fila do dia.")
    return RedirectResponse("/admin", status_code=303)
