"""Senha do painel, sessão, CSRF e proteção das rotas do admin."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import Admin


# --------------------------------------------------------------- senha
def hash_senha(senha: str) -> str:
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), 200_000).hex()
    return f"pbkdf2$200000${sal}${digest}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        _, iteracoes, sal, digest = senha_hash.split("$")
    except ValueError:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), int(iteracoes)).hex()
    return hmac.compare_digest(calculado, digest)


# --------------------------------------------------------------- sessão
class NaoAutenticado(Exception):
    def __init__(self, destino: str):
        self.destino = destino


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


async def verificar_csrf(request: Request) -> None:
    """Dependência para rotas POST: o formulário deve trazer o token da sessão."""
    if request.method not in {"POST", "PUT", "DELETE", "PATCH"}:
        return
    esperado = request.session.get("csrf")
    recebido = request.headers.get("x-csrf-token")
    if recebido is None:
        content_type = request.headers.get("content-type", "")
        if "form" in content_type:
            form = await request.form()
            recebido = form.get("csrf")
        elif "json" in content_type:
            try:
                corpo = await request.json()
                recebido = corpo.get("csrf") if isinstance(corpo, dict) else None
            except Exception:
                recebido = None
    if not esperado or not recebido or not hmac.compare_digest(str(esperado), str(recebido)):
        raise HTTPException(status_code=400, detail="Sessão expirada. Recarregue a página e tente de novo.")


def admin_atual(request: Request, db: Session = Depends(get_db)) -> Admin:
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise NaoAutenticado(str(request.url.path))
    admin = db.get(Admin, admin_id)
    if not admin:
        request.session.pop("admin_id", None)
        raise NaoAutenticado(str(request.url.path))
    return admin


def flash(request: Request, mensagem: str, tipo: str = "ok") -> None:
    lista = request.session.get("flash") or []
    lista.append({"texto": mensagem, "tipo": tipo})
    request.session["flash"] = lista[-5:]


def consumir_flash(request: Request) -> list[dict]:
    lista = request.session.pop("flash", None) or []
    return lista
