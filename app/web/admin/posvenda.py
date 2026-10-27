"""Pós-venda: follow-ups do dia, tickets, devoluções, avaliações e caixa de saída de mensagens."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Avaliacao, FollowUp, Notificacao, Ticket
from ...security import flash
from ...services import assistente, configuracoes, notificacoes, pedidos as svc_pedidos, posvenda as svc
from ...utils import parse_dinheiro, telefone_whatsapp
from ..render import render

router = APIRouter()


@router.get("/pos-venda")
def painel(request: Request, db: Session = Depends(get_db)):
    pendentes = svc.followups_pendentes(db)
    return render(
        request, "admin/posvenda.html", db,
        followups=pendentes, mensagens={f.id: svc.preparar_mensagem(db, f) for f in pendentes},
        futuros=svc.followups_futuros(db), tickets=svc.tickets(db, "abertos"), resolvidos=svc.tickets(db, "resolvido", 20),
        avaliacoes=svc.avaliacoes_pendentes(db),
    )


@router.post("/followups/{followup_id}/concluir")
async def concluir(request: Request, followup_id: int, observacao: str = Form(""), db: Session = Depends(get_db)):
    f = db.get(FollowUp, followup_id)
    svc.concluir_followup(db, f, observacao, registrar_notificacao=False)
    db.commit()
    return RedirectResponse(request.headers.get("referer") or "/admin/pos-venda", status_code=303)


@router.post("/followups/{followup_id}/pular")
async def pular(request: Request, followup_id: int, db: Session = Depends(get_db)):
    svc.pular_followup(db, db.get(FollowUp, followup_id))
    db.commit()
    return RedirectResponse(request.headers.get("referer") or "/admin/pos-venda", status_code=303)


@router.post("/followups/{followup_id}/adiar")
async def adiar(request: Request, followup_id: int, dias: int = Form(2), db: Session = Depends(get_db)):
    svc.adiar_followup(db, db.get(FollowUp, followup_id), dias)
    db.commit()
    return RedirectResponse(request.headers.get("referer") or "/admin/pos-venda", status_code=303)


# ---------------------------------------------------------------- tickets
@router.get("/tickets/novo")
def ticket_novo(request: Request, pedido: str = "", db: Session = Depends(get_db)):
    p = svc_pedidos.por_numero(db, pedido) if pedido else None
    return render(request, "admin/ticket_novo.html", db, pedido=p)


@router.post("/tickets/novo")
async def ticket_novo_enviar(request: Request, tipo: str = Form("duvida"), assunto: str = Form(""), mensagem: str = Form(""), pedido: str = Form(""), nome: str = Form(""), email: str = Form(""), telefone: str = Form(""), db: Session = Depends(get_db)):
    p = svc_pedidos.por_numero(db, pedido) if pedido else None
    t = svc.abrir_ticket(db, tipo, assunto, mensagem, nome=nome, email=email, telefone=telefone, pedido=p, autor="loja")
    db.commit()
    return RedirectResponse(f"/admin/tickets/{t.id}", status_code=303)


@router.get("/tickets/{ticket_id}")
def ticket(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t:
        return RedirectResponse("/admin/pos-venda", status_code=303)
    numero = telefone_whatsapp(t.telefone)
    return render(request, "admin/ticket.html", db, ticket=t, wa_base=f"https://wa.me/{numero}?text=" if numero else "")


@router.post("/tickets/{ticket_id}/responder")
async def responder(request: Request, ticket_id: int, texto: str = Form(""), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if texto.strip():
        svc.responder(db, t, texto)
        db.commit()
    return RedirectResponse(f"/admin/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/resolver")
async def resolver(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    svc.resolver(db, db.get(Ticket, ticket_id))
    db.commit()
    return RedirectResponse(request.headers.get("referer") or "/admin/pos-venda", status_code=303)


@router.post("/tickets/{ticket_id}/reabrir")
async def reabrir(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    svc.reabrir(db, db.get(Ticket, ticket_id))
    db.commit()
    return RedirectResponse(f"/admin/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/devolucao")
async def devolucao(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    form = await request.form()
    itens = {}
    for chave, valor in form.multi_items():
        if chave.startswith("dev_") and valor and int(valor) > 0:
            itens[int(chave[4:])] = int(valor)
    try:
        svc.concluir_devolucao(db, t, itens, parse_dinheiro(form.get("reembolso")), form.get("motivo") or "")
        db.commit()
        flash(request, "Devolução registrada: estoque e caixa atualizados.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(f"/admin/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/sugerir")
async def sugerir(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    historico = "\n".join(f"[{m.autor}] {m.texto}" for m in t.mensagens)
    try:
        texto = assistente.sugerir_resposta_ticket(t.tipo, t.assunto, historico, "Troca ou devolução em até 7 dias após o recebimento (produto lacrado, por higiene). Estorno pelo mesmo PIX em até 2 dias úteis.")
        return JSONResponse({"ok": True, "texto": texto})
    except Exception as exc:
        return JSONResponse({"ok": False, "erro": str(exc)}, status_code=400)


# ------------------------------------------------------------- avaliações
@router.post("/avaliacoes/{avaliacao_id}/aprovar")
async def aprovar(request: Request, avaliacao_id: int, db: Session = Depends(get_db)):
    a = db.get(Avaliacao, avaliacao_id)
    a.aprovada = True
    db.commit()
    return RedirectResponse(request.headers.get("referer") or "/admin/pos-venda", status_code=303)


@router.post("/avaliacoes/{avaliacao_id}/remover")
async def remover(request: Request, avaliacao_id: int, db: Session = Depends(get_db)):
    a = db.get(Avaliacao, avaliacao_id)
    db.delete(a)
    db.commit()
    return RedirectResponse(request.headers.get("referer") or "/admin/pos-venda", status_code=303)


# -------------------------------------------------------------- mensagens
@router.get("/mensagens")
def mensagens(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/mensagens.html", db, pendentes=notificacoes.pendentes(db), smtp_ok=bool(configuracoes.obter(db, "loja_email")))


@router.post("/mensagens/{notificacao_id}/enviada")
async def marcar_enviada(request: Request, notificacao_id: int, db: Session = Depends(get_db)):
    n = db.get(Notificacao, notificacao_id)
    notificacoes.marcar_enviada(db, n)
    db.commit()
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"ok": True})
    return RedirectResponse(request.headers.get("referer") or "/admin/mensagens", status_code=303)
