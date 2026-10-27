"""Relatórios: financeiro, estoque, pedidos, pagos-não-enviados, clientes. Todos com CSV."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import NotaFiscal, Pedido, PedidoItem, StatusNota, StatusPedido
from ..utils import agora, brl, fim_do_dia, inicio_do_dia
from . import caixa, clientes as svc_clientes, estoque


def _pedidos_pagos_no_periodo(db: Session, inicio: date, fim: date) -> list[Pedido]:
    return list(
        db.execute(
            select(Pedido).where(Pedido.status.in_(StatusPedido.PAGOS), Pedido.pago_em >= inicio_do_dia(inicio), Pedido.pago_em <= fim_do_dia(fim)).order_by(Pedido.pago_em)
        ).scalars()
    )


def financeiro(db: Session, inicio: date, fim: date) -> dict:
    pedidos = _pedidos_pagos_no_periodo(db, inicio, fim)
    receita_produtos = sum(p.subtotal_cents - p.desconto_cents for p in pedidos)
    frete_cobrado = sum(p.frete_cents for p in pedidos)
    receita_bruta = sum(p.total_cents for p in pedidos)
    descontos = sum(p.desconto_cents for p in pedidos)
    cmv = sum(p.custo_itens_cents for p in pedidos)
    postagem = sum(p.custo_postagem_cents for p in pedidos)
    margem_bruta = receita_produtos - cmv
    resumo_caixa = caixa.resumo(db, inicio, fim)
    estornos = resumo_caixa["saidas"].get("estorno", 0)
    compras_pagas = resumo_caixa["saidas"].get("compra", 0)
    despesas = sum(v for k, v in resumo_caixa["saidas"].items() if k not in {"compra", "estorno", "frete"})
    por_dia_caixa = caixa.por_dia(db, inicio, fim)
    vendas_dia: dict[date, dict] = defaultdict(lambda: {"pedidos": 0, "total_cents": 0})
    for p in pedidos:
        d = p.pago_em.date()
        vendas_dia[d]["pedidos"] += 1
        vendas_dia[d]["total_cents"] += p.total_cents
    serie = []
    dia = inicio
    while dia <= fim:
        serie.append({"dia": dia, "pedidos": vendas_dia[dia]["pedidos"], "total_cents": vendas_dia[dia]["total_cents"], "saidas_cents": por_dia_caixa.get(dia, {}).get("saida", 0)})
        dia += timedelta(days=1)
    top: dict[str, dict] = {}
    for p in pedidos:
        for i in p.itens:
            linha = top.setdefault(i.nome, {"nome": i.nome, "sku": i.sku, "quantidade": 0, "receita_cents": 0, "margem_cents": 0})
            linha["quantidade"] += i.quantidade
            linha["receita_cents"] += i.total_cents
            linha["margem_cents"] += i.quantidade * (i.preco_unit_cents - i.custo_unit_cents)
    top_produtos = sorted(top.values(), key=lambda l: l["receita_cents"], reverse=True)[:10]
    cancelados = db.execute(
        select(func.count(Pedido.id)).where(Pedido.status == StatusPedido.CANCELADO, Pedido.cancelado_em >= inicio_do_dia(inicio), Pedido.cancelado_em <= fim_do_dia(fim))
    ).scalar() or 0
    notas = db.execute(
        select(func.count(NotaFiscal.id), func.coalesce(func.sum(NotaFiscal.valor_cents), 0)).where(NotaFiscal.status == StatusNota.AUTORIZADA, NotaFiscal.emitida_em >= inicio_do_dia(inicio), NotaFiscal.emitida_em <= fim_do_dia(fim))
    ).one()
    return {
        "inicio": inicio,
        "fim": fim,
        "pedidos": len(pedidos),
        "cancelados": int(cancelados),
        "ticket_medio_cents": int(receita_bruta / len(pedidos)) if pedidos else 0,
        "receita_bruta_cents": receita_bruta,
        "receita_produtos_cents": receita_produtos,
        "frete_cobrado_cents": frete_cobrado,
        "descontos_cents": descontos,
        "cmv_cents": cmv,
        "margem_bruta_cents": margem_bruta,
        "margem_bruta_pct": round(100.0 * margem_bruta / receita_produtos, 1) if receita_produtos else 0.0,
        "postagem_cents": postagem,
        "margem_apos_frete_cents": margem_bruta + frete_cobrado - postagem,
        "estornos_cents": estornos,
        "compras_pagas_cents": compras_pagas,
        "despesas_cents": despesas,
        "caixa": resumo_caixa,
        "serie": serie,
        "top_produtos": top_produtos,
        "nfe_quantidade": int(notas[0] or 0),
        "nfe_total_cents": int(notas[1] or 0),
        "lista_pedidos": pedidos,
    }


def pedidos(db: Session, inicio: date, fim: date, status: str | None = None) -> dict:
    q = select(Pedido).where(Pedido.criado_em >= inicio_do_dia(inicio), Pedido.criado_em <= fim_do_dia(fim)).order_by(Pedido.id.desc())
    if status:
        q = q.where(Pedido.status == status)
    lista = list(db.execute(q).scalars())
    por_status: dict[str, dict] = defaultdict(lambda: {"quantidade": 0, "total_cents": 0})
    for p in lista:
        por_status[p.status]["quantidade"] += 1
        por_status[p.status]["total_cents"] += p.total_cents
    return {
        "lista": lista,
        "total": len(lista),
        "total_cents": sum(p.total_cents for p in lista),
        "por_status": [{"status": s, "label": StatusPedido.LABELS.get(s, s), **v} for s, v in por_status.items()],
        "itens": sum(p.quantidade_itens for p in lista),
    }


def nao_enviados(db: Session) -> list[dict]:
    lista = list(db.execute(select(Pedido).where(Pedido.status.in_(StatusPedido.PAGOS_NAO_ENVIADOS)).order_by(Pedido.pago_em)).scalars())
    agora_ = agora()
    saida = []
    for p in lista:
        horas = int((agora_ - (p.pago_em or p.criado_em)).total_seconds() // 3600)
        saida.append({"pedido": p, "horas": horas, "atrasado": horas >= 48, "alerta": 24 <= horas < 48})
    return saida


def estoque_posicao(db: Session) -> dict:
    linhas = estoque.posicao(db, somente_ativos=False)
    return {
        "linhas": linhas,
        "valor_custo_cents": sum(l["valor_custo_cents"] for l in linhas if l["produto"].ativo),
        "valor_venda_cents": sum(l["valor_venda_cents"] for l in linhas if l["produto"].ativo),
        "unidades": sum(l["produto"].estoque for l in linhas if l["produto"].ativo),
        "repor": [l for l in linhas if l["precisa_repor"]],
        "parados": [l for l in linhas if l["produto"].ativo and l["produto"].estoque > 0 and l["vendidos_30d"] == 0],
        "movimentos": estoque.movimentos_recentes(db, 40),
    }


def clientes(db: Session) -> dict:
    return svc_clientes.insights(db)


# -------------------------------------------------------------------- CSV
def csv_bytes(cabecalho: list[str], linhas: list[list]) -> bytes:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\n")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow(linha)
    return ("﻿" + buffer.getvalue()).encode("utf-8")  # BOM: Excel abre com acentos certos


def reais(centavos: int) -> str:
    return f"{centavos / 100:.2f}".replace(".", ",")
