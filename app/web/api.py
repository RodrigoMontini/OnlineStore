"""Endpoints JSON usados pelo site (frete, cupom) e webhook de pagamento."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..config import config
from ..db import get_db
from ..services import frete, pedidos as svc_pedidos

router = APIRouter(prefix="/api")


@router.get("/frete")
def api_frete(request: Request, cep: str = "", db: Session = Depends(get_db)):
    carrinho = request.session.get("carrinho") or {}
    linhas = svc_pedidos.itens_do_carrinho(db, carrinho)
    totais = svc_pedidos.totais_carrinho(linhas)
    return frete.cotar(db, cep, totais["subtotal_cents"], totais["peso_g"])


@router.get("/cupom")
def api_cupom(request: Request, codigo: str = "", db: Session = Depends(get_db)):
    carrinho = request.session.get("carrinho") or {}
    linhas = svc_pedidos.itens_do_carrinho(db, carrinho)
    totais = svc_pedidos.totais_carrinho(linhas)
    cupom, desconto, erro = svc_pedidos.aplicar_cupom(db, codigo, totais["subtotal_cents"])
    if erro:
        return {"ok": False, "erro": erro}
    return {"ok": True, "codigo": cupom.codigo if cupom else "", "desconto_cents": desconto, "tipo": cupom.tipo if cupom else ""}


@router.post("/webhooks/pagamento")
async def webhook_pagamento(request: Request, db: Session = Depends(get_db)):
    """Para ligar um PSP depois: POST JSON {"token": WEBHOOK_TOKEN, "pedido": "P1001", "referencia": "..."}."""
    if not config.WEBHOOK_TOKEN:
        return JSONResponse({"ok": False, "erro": "WEBHOOK_TOKEN não configurado"}, status_code=403)
    corpo = await request.json()
    token = str(corpo.get("token", ""))
    if not hmac.compare_digest(token, config.WEBHOOK_TOKEN):
        return JSONResponse({"ok": False, "erro": "token inválido"}, status_code=403)
    pedido = svc_pedidos.por_numero(db, str(corpo.get("pedido", "")))
    if not pedido:
        return JSONResponse({"ok": False, "erro": "pedido não encontrado"}, status_code=404)
    try:
        svc_pedidos.confirmar_pagamento(db, pedido, provedor=str(corpo.get("provedor", "webhook")), referencia=str(corpo.get("referencia", "")))
        db.commit()
    except svc_pedidos.ErroPedido as exc:
        db.rollback()
        return JSONResponse({"ok": False, "erro": str(exc)}, status_code=409)
    return {"ok": True, "status": pedido.status}
