"""Compras de mercadoria: pedido ao fornecedor → recebimento (entra estoque) → pagamento (sai caixa)."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Compra, CompraItem, Fornecedor, Produto, StatusCompra, TipoMovimento
from ..utils import agora, hoje
from . import caixa, estoque


def _proximo_numero(db: Session) -> str:
    total = db.execute(select(func.count(Compra.id))).scalar() or 0
    return f"C{1001 + total}"


def criar(db: Session, fornecedor_id: int | None, observacoes: str = "") -> Compra:
    compra = Compra(numero=_proximo_numero(db), fornecedor_id=fornecedor_id, observacoes=observacoes)
    db.add(compra)
    db.flush()
    return compra


def adicionar_item(db: Session, compra: Compra, produto: Produto, quantidade: int, custo_unit_cents: int | None = None) -> CompraItem:
    if compra.status not in {StatusCompra.RASCUNHO, StatusCompra.ENVIADA}:
        raise ValueError("Esta compra já foi recebida ou cancelada.")
    for item in compra.itens:
        if item.produto_id == produto.id:
            item.quantidade += quantidade
            if custo_unit_cents is not None:
                item.custo_unit_cents = custo_unit_cents
            db.flush()
            return item
    item = CompraItem(
        compra_id=compra.id,
        produto_id=produto.id,
        quantidade=max(1, quantidade),
        custo_unit_cents=produto.custo_cents if custo_unit_cents is None else custo_unit_cents,
    )
    db.add(item)
    db.flush()
    return item


def remover_item(db: Session, compra: Compra, item_id: int) -> None:
    for item in list(compra.itens):
        if item.id == item_id:
            compra.itens.remove(item)
            db.delete(item)
    db.flush()


def enviar(db: Session, compra: Compra) -> None:
    if not compra.itens:
        raise ValueError("Adicione itens antes de enviar a compra.")
    compra.status = StatusCompra.ENVIADA
    compra.enviada_em = agora()
    prazo = compra.fornecedor.prazo_dias if compra.fornecedor else 7
    compra.previsao_entrega = hoje() + timedelta(days=prazo)
    db.flush()


def receber(db: Session, compra: Compra, quantidades: dict[int, int] | None = None, frete_cents: int | None = None) -> None:
    """Dá entrada no estoque e recalcula o custo médio de cada produto."""
    if compra.status == StatusCompra.RECEBIDA:
        raise ValueError("Compra já recebida.")
    if compra.status == StatusCompra.CANCELADA:
        raise ValueError("Compra cancelada.")
    if frete_cents is not None:
        compra.frete_cents = frete_cents
    for item in compra.itens:
        qtd = item.quantidade if quantidades is None else int(quantidades.get(item.id, item.quantidade))
        if qtd <= 0:
            continue
        produto = item.produto
        estoque_anterior = max(produto.estoque, 0)
        custo_anterior = produto.custo_cents
        # custo médio ponderado
        if estoque_anterior + qtd > 0:
            produto.custo_cents = int(round((estoque_anterior * custo_anterior + qtd * item.custo_unit_cents) / (estoque_anterior + qtd)))
        item.recebido = qtd
        estoque.movimentar(db, produto, qtd, TipoMovimento.COMPRA, ref_tipo="compra", ref_id=compra.id, observacao=f"Compra {compra.numero}")
    compra.status = StatusCompra.RECEBIDA
    compra.recebida_em = agora()
    db.flush()


def pagar(db: Session, compra: Compra) -> None:
    if compra.pago:
        return
    compra.pago = True
    compra.paga_em = agora()
    nome = compra.fornecedor.nome if compra.fornecedor else "fornecedor"
    caixa.lancar(db, "saida", "compra", compra.total_cents, f"Compra {compra.numero} — {nome}", ref_tipo="compra", ref_id=compra.id)
    db.flush()


def cancelar(db: Session, compra: Compra) -> None:
    if compra.status == StatusCompra.RECEBIDA:
        raise ValueError("Compra já recebida não pode ser cancelada; faça um ajuste de estoque.")
    compra.status = StatusCompra.CANCELADA
    db.flush()


def listar(db: Session, status: str | None = None, limite: int = 200) -> list[Compra]:
    q = select(Compra).order_by(Compra.id.desc()).limit(limite)
    if status:
        q = q.where(Compra.status == status)
    return list(db.execute(q).scalars())


def criar_sugeridas(db: Session) -> list[Compra]:
    """Uma compra rascunho por fornecedor com tudo que precisa repor."""
    por_fornecedor: dict[int | None, list[dict]] = defaultdict(list)
    for linha in estoque.para_repor(db):
        if linha["sugestao_compra"] > 0:
            por_fornecedor[linha["produto"].fornecedor_id].append(linha)
    compras: list[Compra] = []
    for fornecedor_id, linhas in por_fornecedor.items():
        compra = criar(db, fornecedor_id, observacoes="Sugerida automaticamente pelo painel (reposição de estoque).")
        for linha in linhas:
            adicionar_item(db, compra, linha["produto"], linha["sugestao_compra"])
        compras.append(compra)
    db.flush()
    return compras


def a_pagar(db: Session) -> list[Compra]:
    return list(db.execute(select(Compra).where(Compra.status == StatusCompra.RECEBIDA, Compra.pago.is_(False)).order_by(Compra.recebida_em)).scalars())


def fornecedores(db: Session) -> list[Fornecedor]:
    return list(db.execute(select(Fornecedor).where(Fornecedor.ativo.is_(True)).order_by(Fornecedor.nome)).scalars())
