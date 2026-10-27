"""Relatórios com exportação CSV (abre no Excel/Numbers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import StatusPedido
from ...services import relatorios as svc
from ...utils import fmt_cpf, fmt_data, fmt_datahora, periodo
from ..render import render

router = APIRouter(prefix="/relatorios")


def _csv(nome: str, cabecalho: list[str], linhas: list[list]) -> Response:
    return Response(svc.csv_bytes(cabecalho, linhas), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})


@router.get("")
def hub(request: Request, db: Session = Depends(get_db)):
    inicio, fim, _ = periodo("mes")
    return render(request, "admin/relatorios.html", db, fin=svc.financeiro(db, inicio, fim), nao_enviados=len(svc.nao_enviados(db)))


@router.get("/financeiro")
def financeiro(request: Request, p: str = "30d", inicio: str = "", fim: str = "", formato: str = "", db: Session = Depends(get_db)):
    di, df, rotulo = periodo(p, inicio, fim)
    dados = svc.financeiro(db, di, df)
    if formato == "csv":
        linhas = [[fmt_data(l["dia"]), l["pedidos"], svc.reais(l["total_cents"]), svc.reais(l["saidas_cents"])] for l in dados["serie"]]
        return _csv(f"financeiro_{di}_{df}", ["Dia", "Pedidos pagos", "Receita (R$)", "Saídas de caixa (R$)"], linhas)
    if formato == "csv_pedidos":
        linhas = [[pd.numero, fmt_datahora(pd.pago_em), pd.nome, fmt_cpf(pd.cpf), svc.reais(pd.subtotal_cents), svc.reais(pd.desconto_cents), svc.reais(pd.frete_cents), svc.reais(pd.total_cents), svc.reais(pd.custo_itens_cents), pd.label] for pd in dados["lista_pedidos"]]
        return _csv(f"vendas_{di}_{df}", ["Pedido", "Pago em", "Cliente", "CPF", "Produtos", "Desconto", "Frete", "Total", "Custo", "Status"], linhas)
    max_dia = max((l["total_cents"] for l in dados["serie"]), default=0) or 1
    return render(request, "admin/rel_financeiro.html", db, dados=dados, p=p, rotulo=rotulo, inicio=di, fim=df, max_dia=max_dia)


@router.get("/estoque")
def estoque(request: Request, formato: str = "", db: Session = Depends(get_db)):
    dados = svc.estoque_posicao(db)
    if formato == "csv":
        linhas = [[l["produto"].sku, l["produto"].nome, l["produto"].categoria.nome if l["produto"].categoria else "", l["produto"].estoque, l["produto"].estoque_minimo, svc.reais(l["produto"].custo_cents), svc.reais(l["valor_custo_cents"]), svc.reais(l["produto"].preco_cents), l["vendidos_30d"], l["cobertura_dias"] if l["cobertura_dias"] is not None else "", "sim" if l["precisa_repor"] else "", l["sugestao_compra"], "ativo" if l["produto"].ativo else "inativo"] for l in dados["linhas"]]
        return _csv("estoque", ["SKU", "Produto", "Categoria", "Estoque", "Mínimo", "Custo unit.", "Valor a custo", "Preço", "Vendidos 30d", "Cobertura (dias)", "Repor", "Sugestão compra", "Situação"], linhas)
    return render(request, "admin/rel_estoque.html", db, dados=dados)


@router.get("/pedidos")
def pedidos(request: Request, p: str = "30d", inicio: str = "", fim: str = "", status: str = "", formato: str = "", db: Session = Depends(get_db)):
    di, df, rotulo = periodo(p, inicio, fim)
    dados = svc.pedidos(db, di, df, status or None)
    if formato == "csv":
        linhas = [[pd.numero, fmt_datahora(pd.criado_em), pd.label, pd.nome, pd.email, pd.cidade, pd.uf, pd.quantidade_itens, svc.reais(pd.total_cents), pd.frete_metodo, pd.rastreio, fmt_datahora(pd.pago_em), fmt_datahora(pd.enviado_em)] for pd in dados["lista"]]
        return _csv(f"pedidos_{di}_{df}", ["Pedido", "Criado em", "Status", "Cliente", "E-mail", "Cidade", "UF", "Itens", "Total", "Envio", "Rastreio", "Pago em", "Enviado em"], linhas)
    return render(request, "admin/rel_pedidos.html", db, dados=dados, p=p, rotulo=rotulo, inicio=di, fim=df, status=status, labels=StatusPedido.LABELS)


@router.get("/nao-enviados")
def nao_enviados(request: Request, formato: str = "", db: Session = Depends(get_db)):
    linhas = svc.nao_enviados(db)
    if formato == "csv":
        return _csv("pagos_nao_enviados", ["Pedido", "Pago em", "Horas desde o pagamento", "Status", "Cliente", "Cidade/UF", "Total"], [[l["pedido"].numero, fmt_datahora(l["pedido"].pago_em), l["horas"], l["pedido"].label, l["pedido"].nome, f"{l['pedido'].cidade}/{l['pedido'].uf}", svc.reais(l["pedido"].total_cents)] for l in linhas])
    return render(request, "admin/rel_nao_enviados.html", db, linhas=linhas)


@router.get("/clientes")
def clientes(request: Request, formato: str = "", db: Session = Depends(get_db)):
    dados = svc.clientes(db)
    if formato == "csv":
        linhas = [[l["cliente"].nome, l["cliente"].email, l["cliente"].telefone, fmt_cpf(l["cliente"].cpf), l["idade"] or "", f"{l['cliente'].cidade}/{l['cliente'].uf}", l["pedidos_pagos"], svc.reais(l["ltv_cents"]), fmt_data(l["ultimo_pedido"]), "sim" if l["kyc_ok"] else "não", "sim" if l["cliente"].aceita_marketing else "não"] for l in dados["linhas"]]
        return _csv("clientes", ["Nome", "E-mail", "Telefone", "CPF", "Idade", "Cidade/UF", "Pedidos pagos", "Total comprado", "Último pedido", "KYC completo", "Aceita novidades"], linhas)
    return render(request, "admin/rel_clientes.html", db, dados=dados)
