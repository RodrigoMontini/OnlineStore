"""Faturamento: notas emitidas, pendências, DANFE e CSV para o contador."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import NotaFiscal, Pedido
from ...security import flash
from ...services import faturamento as svc, relatorios
from ...utils import fmt_cpf, fmt_datahora, periodo
from ..render import render

router = APIRouter(prefix="/faturamento")


@router.get("")
def painel(request: Request, status: str = "", p: str = "mes", inicio: str = "", fim: str = "", formato: str = "", db: Session = Depends(get_db)):
    di, df, rotulo = periodo(p, inicio, fim)
    notas = svc.listar(db, status or None, di, df)
    if formato == "csv":
        linhas = [[n.numero, n.serie, n.chave, fmt_datahora(n.emitida_em), n.pedido.numero, n.pedido.nome, fmt_cpf(n.pedido.cpf), n.pedido.uf, relatorios.reais(n.valor_cents), n.label, n.ambiente, n.protocolo, n.xml_url] for n in notas]
        return Response(relatorios.csv_bytes(["Número", "Série", "Chave", "Emitida em", "Pedido", "Cliente", "CPF", "UF", "Valor", "Status", "Ambiente", "Protocolo", "XML"], linhas), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="notas_{di}_{df}.csv"'})
    return render(
        request, "admin/faturamento.html", db, notas=notas, status=status, p=p, rotulo=rotulo, inicio=di, fim=df,
        pendentes=svc.pendentes(db), por_mes=svc.faturamento_por_mes(db), faltas=svc.dados_fiscais_ok(db),
        total_periodo=sum(n.valor_cents for n in notas if n.status == "autorizada"),
    )


@router.post("/emitir/{pedido_id}")
async def emitir(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.get(Pedido, pedido_id)
    try:
        nota = svc.emitir(db, pedido)
        db.commit()
        flash(request, f"NF-e {nota.numero}: {nota.label}." + (f" {nota.mensagem}" if nota.status == "erro" else ""), "ok" if nota.status != "erro" else "erro")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(request.headers.get("referer") or "/admin/faturamento", status_code=303)


@router.post("/emitir-pendentes")
async def emitir_pendentes(request: Request, db: Session = Depends(get_db)):
    ok, erros = 0, []
    for pedido in svc.pendentes(db):
        try:
            nota = svc.emitir(db, pedido)
            if nota.status == "erro":
                erros.append(f"{pedido.numero}: {nota.mensagem}")
            else:
                ok += 1
        except Exception as exc:
            erros.append(f"{pedido.numero}: {exc}")
    db.commit()
    flash(request, f"{ok} nota(s) emitida(s)." + (" Falhas: " + "; ".join(erros[:5]) if erros else ""), "ok" if not erros else "aviso")
    return RedirectResponse("/admin/faturamento", status_code=303)


@router.post("/{nota_id}/consultar")
async def consultar(request: Request, nota_id: int, db: Session = Depends(get_db)):
    nota = db.get(NotaFiscal, nota_id)
    svc.consultar(db, nota)
    db.commit()
    flash(request, f"NF-e {nota.numero}: {nota.label}. {nota.mensagem}".strip())
    return RedirectResponse(request.headers.get("referer") or "/admin/faturamento", status_code=303)


@router.post("/{nota_id}/cancelar")
async def cancelar(request: Request, nota_id: int, justificativa: str = Form(""), db: Session = Depends(get_db)):
    nota = db.get(NotaFiscal, nota_id)
    try:
        svc.cancelar(db, nota, justificativa)
        db.commit()
        flash(request, f"NF-e {nota.numero} cancelada.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(request.headers.get("referer") or "/admin/faturamento", status_code=303)


@router.get("/{nota_id}/danfe")
def danfe(request: Request, nota_id: int, db: Session = Depends(get_db)):
    nota = db.get(NotaFiscal, nota_id)
    if nota.danfe_url and nota.provedor != "simulado":
        return RedirectResponse(nota.danfe_url, status_code=302)
    payload = json.loads(nota.payload_json) if nota.payload_json else {}
    return render(request, "impressao/danfe.html", db, nota=nota, payload=payload)
