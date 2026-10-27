"""Painel 'Hoje': a fila de trabalho do dia e os números que importam."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...db import get_db
from ...services import automacoes, configuracoes, posvenda
from ..render import render

router = APIRouter()


@router.get("/")
@router.get("/hoje")
def hoje(request: Request, db: Session = Depends(get_db)):
    automacoes.executar(db)
    db.commit()
    tarefas = automacoes.tarefas_hoje(db)
    kpis = automacoes.kpis(db)
    mensagens = {f.id: posvenda.preparar_mensagem(db, f) for f in tarefas["followups"]}
    cfg = configuracoes.obter_todas(db)
    avisos = []
    if not cfg["pix_chave"]:
        avisos.append(("Sem chave PIX: os pedidos nascem sem QR code.", "/admin/configuracoes#pix"))
    if not cfg["remetente_cep"]:
        avisos.append(("Preencha o endereço do remetente para imprimir etiquetas.", "/admin/configuracoes#remetente"))
    return render(request, "admin/hoje.html", db, tarefas=tarefas, kpis=kpis, mensagens=mensagens, avisos=avisos, loja=cfg)
