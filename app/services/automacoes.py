"""O 'cérebro' da operação de uma pessoa só.

- executar(): regras que rodam sozinhas (de 10 em 10 minutos e a cada abertura do painel).
- tarefas_hoje(): a fila do dia, na ordem em que vale a pena atacar.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Avaliacao, FollowUp, Pedido, StatusPedido, Ticket, TipoFollowUp
from ..utils import agora, hoje
from . import caixa, compras, configuracoes, estoque, faturamento, pedidos as svc_pedidos, posvenda


def executar(db: Session) -> dict:
    """Idempotente: pode rodar quantas vezes quiser."""
    resultado = {"cancelados": 0, "followups": 0}
    horas = configuracoes.obter_int(db, "cancelar_nao_pago_horas", 24)
    if horas > 0:
        limite = agora() - timedelta(hours=horas)
        limite_informado = agora() - timedelta(hours=horas * 3)
        for pedido in db.execute(select(Pedido).where(Pedido.status == StatusPedido.AGUARDANDO, Pedido.criado_em <= limite)).scalars():
            if pedido.cliente_informou_pagamento and pedido.criado_em > limite_informado:
                continue  # o cliente disse que pagou: dá mais tempo para conferir
            svc_pedidos.cancelar(db, pedido, motivo=f"PIX não identificado em {horas} h", estornar=False, avisar=False)
            resultado["cancelados"] += 1
    # Pedidos enviados sem follow-up de entrega (ex.: enviados antes da regra existir)
    for pedido in db.execute(select(Pedido).where(Pedido.status == StatusPedido.ENVIADO)).scalars():
        if not any(f.tipo == TipoFollowUp.CONFIRMAR_ENTREGA for f in pedido.followups):
            prazo = max(pedido.frete_prazo_dias, 1) + 2
            svc_pedidos._criar_followup(db, pedido, TipoFollowUp.CONFIRMAR_ENTREGA, (pedido.enviado_em or agora()).date() + timedelta(days=prazo))
            resultado["followups"] += 1
    configuracoes.definir(db, "ultima_automacao", agora().isoformat())
    db.flush()
    return resultado


def kpis(db: Session) -> dict:
    h = hoje()
    def vendas(desde, ate=None):
        q = select(func.count(Pedido.id), func.coalesce(func.sum(Pedido.total_cents), 0), func.coalesce(func.sum(Pedido.subtotal_cents - Pedido.desconto_cents), 0)).where(
            Pedido.status.in_(StatusPedido.PAGOS), Pedido.pago_em >= desde.strftime("%Y-%m-%d 00:00:00")
        )
        if ate:
            q = q.where(Pedido.pago_em <= ate.strftime("%Y-%m-%d 23:59:59"))
        n, total, produtos = db.execute(q).one()
        return {"pedidos": int(n or 0), "total_cents": int(total or 0), "produtos_cents": int(produtos or 0)}

    v_hoje = vendas(h)
    v_7 = vendas(h - timedelta(days=6))
    v_30 = vendas(h - timedelta(days=29))
    cmv_30 = db.execute(
        select(func.coalesce(func.sum(Pedido.id * 0), 0))
    ).scalar()  # placeholder para manter uma consulta simples abaixo
    pedidos_30 = db.execute(select(Pedido).where(Pedido.status.in_(StatusPedido.PAGOS), Pedido.pago_em >= (h - timedelta(days=29)).strftime("%Y-%m-%d 00:00:00"))).scalars()
    custo_30 = 0
    for p in pedidos_30:
        custo_30 += p.custo_itens_cents
    margem_30 = v_30["produtos_cents"] - custo_30
    serie = []
    for i in range(13, -1, -1):
        d = h - timedelta(days=i)
        serie.append({"dia": d, **vendas(d, d)})
    return {
        "hoje": v_hoje,
        "sete_dias": v_7,
        "trinta_dias": v_30,
        "ticket_medio_cents": int(v_30["total_cents"] / v_30["pedidos"]) if v_30["pedidos"] else 0,
        "margem_30_cents": margem_30,
        "margem_30_pct": round(100.0 * margem_30 / v_30["produtos_cents"], 1) if v_30["produtos_cents"] else 0.0,
        "saldo_caixa_cents": caixa.saldo(db),
        "valor_estoque_cents": estoque.valor_total_custo(db),
        "serie_14d": serie,
    }


def tarefas_hoje(db: Session) -> dict:
    aguardando = svc_pedidos.listar(db, status=StatusPedido.AGUARDANDO, limite=200)
    aguardando.sort(key=lambda p: (not p.cliente_informou_pagamento, p.criado_em))
    a_separar = svc_pedidos.listar(db, status=StatusPedido.PAGO, limite=200)
    a_embalar = svc_pedidos.listar(db, status=StatusPedido.SEPARADO, limite=200)
    a_postar = svc_pedidos.listar(db, status=StatusPedido.EMBALADO, limite=200)
    em_transito = svc_pedidos.listar(db, status=StatusPedido.ENVIADO, limite=200)
    atrasados = [p for p in em_transito if p.enviado_em and (agora() - p.enviado_em).days > max(p.frete_prazo_dias, 1) + 3]
    followups = posvenda.followups_pendentes(db)
    tickets = posvenda.tickets(db, status="abertos")
    repor = estoque.para_repor(db)
    notas_pendentes = faturamento.pendentes(db)
    compras_a_pagar = compras.a_pagar(db)
    avaliacoes = posvenda.avaliacoes_pendentes(db)
    a_separar_lista = sorted(a_separar, key=lambda p: p.pago_em or p.criado_em)
    for lista in (a_separar_lista, a_embalar, a_postar):
        lista.sort(key=lambda p: p.pago_em or p.criado_em)
    return {
        "aguardando": aguardando,
        "a_separar": a_separar_lista,
        "a_embalar": a_embalar,
        "a_postar": a_postar,
        "em_transito": em_transito,
        "atrasados": atrasados,
        "followups": followups,
        "tickets": tickets,
        "repor": repor,
        "notas_pendentes": notas_pendentes,
        "compras_a_pagar": compras_a_pagar,
        "avaliacoes": avaliacoes,
        "total_acoes": len(aguardando) + len(a_separar) + len(a_embalar) + len(a_postar) + len(atrasados) + len(followups) + len(tickets) + len(notas_pendentes) + len(compras_a_pagar),
        "nao_enviados": len(a_separar) + len(a_embalar) + len(a_postar),
    }
