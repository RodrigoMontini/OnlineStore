"""Estoque: cada mudança gera um movimento, e o saldo do produto acompanha."""
from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import MovimentoEstoque, Pedido, PedidoItem, Produto, StatusPedido, TipoMovimento
from ..utils import agora
from . import configuracoes


class EstoqueInsuficiente(Exception):
    def __init__(self, produto: Produto, pedido_qtd: int):
        self.produto = produto
        self.pedido_qtd = pedido_qtd
        super().__init__(f"Estoque insuficiente de {produto.nome}: pedido {pedido_qtd}, disponível {produto.estoque}")


def movimentar(
    db: Session,
    produto: Produto,
    quantidade: int,
    tipo: str,
    ref_tipo: str = "",
    ref_id: int | None = None,
    observacao: str = "",
    permitir_negativo: bool = False,
) -> MovimentoEstoque:
    if quantidade == 0:
        raise ValueError("Quantidade zero")
    novo_saldo = produto.estoque + quantidade
    if novo_saldo < 0 and not permitir_negativo:
        raise EstoqueInsuficiente(produto, -quantidade)
    produto.estoque = novo_saldo
    mov = MovimentoEstoque(
        produto_id=produto.id,
        quantidade=quantidade,
        tipo=tipo,
        ref_tipo=ref_tipo,
        ref_id=ref_id,
        observacao=observacao[:200],
        saldo_apos=novo_saldo,
    )
    db.add(mov)
    db.flush()
    return mov


def ajustar_para(db: Session, produto: Produto, novo_saldo: int, observacao: str = "Contagem") -> MovimentoEstoque | None:
    diferenca = novo_saldo - produto.estoque
    if diferenca == 0:
        return None
    tipo = TipoMovimento.AJUSTE if diferenca > 0 else TipoMovimento.PERDA if "perda" in observacao.lower() else TipoMovimento.AJUSTE
    return movimentar(db, produto, diferenca, tipo, observacao=observacao, permitir_negativo=True)


def vendas_por_produto(db: Session, dias: int = 30) -> dict[int, int]:
    """Quantidade vendida (pedidos pagos) por produto nos últimos N dias."""
    desde = agora() - timedelta(days=dias)
    linhas = db.execute(
        select(PedidoItem.produto_id, func.sum(PedidoItem.quantidade))
        .join(Pedido, Pedido.id == PedidoItem.pedido_id)
        .where(Pedido.status.in_(StatusPedido.PAGOS), Pedido.pago_em >= desde, PedidoItem.produto_id.is_not(None))
        .group_by(PedidoItem.produto_id)
    ).all()
    return {int(pid): int(qtd or 0) for pid, qtd in linhas}


def reservado_por_produto(db: Session) -> dict[int, int]:
    """Quantidade em pedidos aguardando pagamento (ainda não baixou do estoque)."""
    linhas = db.execute(
        select(PedidoItem.produto_id, func.sum(PedidoItem.quantidade))
        .join(Pedido, Pedido.id == PedidoItem.pedido_id)
        .where(Pedido.status == StatusPedido.AGUARDANDO, PedidoItem.produto_id.is_not(None))
        .group_by(PedidoItem.produto_id)
    ).all()
    return {int(pid): int(qtd or 0) for pid, qtd in linhas}


def posicao(db: Session, somente_ativos: bool = True) -> list[dict]:
    """Posição de estoque com giro, cobertura e sugestão de compra."""
    vendas30 = vendas_por_produto(db, 30)
    reservas = reservado_por_produto(db)
    cobertura_min = configuracoes.obter_int(db, "cobertura_minima_dias", 14)
    lead_padrao = configuracoes.obter_int(db, "lead_time_padrao_dias", 7)
    q = select(Produto).order_by(Produto.nome)
    if somente_ativos:
        q = q.where(Produto.ativo.is_(True))
    linhas = []
    for p in db.execute(q).scalars():
        vendidos = vendas30.get(p.id, 0)
        media_dia = vendidos / 30.0
        cobertura = math.inf if media_dia == 0 else p.estoque / media_dia
        lead = p.fornecedor.prazo_dias if p.fornecedor else lead_padrao
        # Repor quando o estoque não cobre o prazo do fornecedor + cobertura mínima, ou está no mínimo.
        horizonte_dias = lead + cobertura_min
        necessario = math.ceil(media_dia * horizonte_dias) + p.estoque_minimo
        sugestao = max(0, necessario - p.estoque)
        precisa_repor = p.estoque <= p.estoque_minimo or (media_dia > 0 and cobertura < horizonte_dias)
        if not precisa_repor:
            sugestao = 0
        elif sugestao == 0:
            sugestao = max(p.estoque_minimo * 2 - p.estoque, 1)
        linhas.append(
            {
                "produto": p,
                "vendidos_30d": vendidos,
                "media_dia": round(media_dia, 2),
                "cobertura_dias": None if cobertura == math.inf else int(cobertura),
                "reservado": reservas.get(p.id, 0),
                "valor_custo_cents": p.estoque * p.custo_cents,
                "valor_venda_cents": p.estoque * p.preco_cents,
                "precisa_repor": precisa_repor,
                "sugestao_compra": sugestao,
                "lead_dias": lead,
            }
        )
    return linhas


def para_repor(db: Session) -> list[dict]:
    return [linha for linha in posicao(db) if linha["precisa_repor"]]


def movimentos_recentes(db: Session, limite: int = 50, produto_id: int | None = None) -> list[MovimentoEstoque]:
    q = select(MovimentoEstoque).order_by(MovimentoEstoque.id.desc()).limit(limite)
    if produto_id:
        q = q.where(MovimentoEstoque.produto_id == produto_id)
    return list(db.execute(q).scalars())


def valor_total_custo(db: Session) -> int:
    return int(db.execute(select(func.coalesce(func.sum(Produto.estoque * Produto.custo_cents), 0)).where(Produto.ativo.is_(True))).scalar() or 0)
