"""Pedidos: do carrinho ao entregue.

Fluxo: aguardando_pagamento → pago → separado → embalado → enviado → entregue.
O estoque baixa quando o pagamento é confirmado; o caixa recebe no mesmo momento.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Cliente, Cupom, FollowUp, Pagamento, Pedido, PedidoItem, Produto, StatusNota, StatusPedido,
    TipoFollowUp, TipoMovimento,
)
from ..utils import agora, hoje, so_digitos, token_url
from . import caixa, configuracoes, estoque, notificacoes, pagamentos


class ErroPedido(Exception):
    pass


# ----------------------------------------------------------------- carrinho
def itens_do_carrinho(db: Session, carrinho: dict[str, int]) -> list[dict]:
    """carrinho = {produto_id: quantidade} (vem do cookie de sessão)."""
    if not carrinho:
        return []
    ids = [int(k) for k in carrinho.keys() if str(k).isdigit()]
    produtos = {p.id: p for p in db.execute(select(Produto).where(Produto.id.in_(ids), Produto.ativo.is_(True))).scalars()}
    linhas = []
    for pid, qtd in carrinho.items():
        p = produtos.get(int(pid)) if str(pid).isdigit() else None
        if not p or int(qtd) <= 0:
            continue
        qtd = min(int(qtd), max(p.estoque, 0)) if p.estoque > 0 else 0
        linhas.append({"produto": p, "quantidade": qtd, "total_cents": qtd * p.preco_cents, "sem_estoque": p.estoque <= 0, "ajustado": qtd != int(carrinho[pid])})
    return linhas


def totais_carrinho(linhas: list[dict]) -> dict:
    subtotal = sum(l["total_cents"] for l in linhas)
    peso = sum(l["quantidade"] * l["produto"].peso_g for l in linhas)
    return {"subtotal_cents": subtotal, "peso_g": peso, "quantidade": sum(l["quantidade"] for l in linhas)}


def aplicar_cupom(db: Session, codigo: str, subtotal_cents: int) -> tuple[Cupom | None, int, str]:
    """Retorna (cupom, desconto_cents, erro)."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None, 0, ""
    cupom = db.execute(select(Cupom).where(Cupom.codigo == codigo)).scalar_one_or_none()
    if not cupom or not cupom.ativo:
        return None, 0, "Cupom não encontrado."
    if cupom.validade and cupom.validade < hoje():
        return None, 0, "Cupom vencido."
    if cupom.max_usos and cupom.usos >= cupom.max_usos:
        return None, 0, "Cupom esgotado."
    if subtotal_cents < cupom.minimo_cents:
        return None, 0, f"Cupom vale para compras acima de {cupom.minimo_cents / 100:.2f}."
    if cupom.tipo == "percentual":
        desconto = int(round(subtotal_cents * cupom.valor / 100.0))
    elif cupom.tipo == "fixo":
        desconto = min(cupom.valor, subtotal_cents)
    else:  # frete
        desconto = 0
    return cupom, desconto, ""


# ------------------------------------------------------------------ criação
def _proximo_numero(db: Session) -> str:
    maior = db.execute(select(func.max(Pedido.id))).scalar() or 0
    return f"P{1000 + maior + 1}"


def criar(
    db: Session,
    linhas: list[dict],
    cliente: Cliente,
    dados: dict,
    frete_opcao: dict,
    cupom_codigo: str = "",
    origem: str = "site",
) -> Pedido:
    if not linhas:
        raise ErroPedido("Seu carrinho está vazio.")
    for l in linhas:
        p = l["produto"]
        if l["quantidade"] <= 0 or p.estoque < l["quantidade"]:
            raise ErroPedido(f"Não temos {l['quantidade']} unidade(s) de {p.nome} em estoque agora.")
    tot = totais_carrinho(linhas)
    cupom, desconto, erro_cupom = aplicar_cupom(db, cupom_codigo, tot["subtotal_cents"])
    if erro_cupom:
        raise ErroPedido(erro_cupom)
    frete_cents = int(frete_opcao.get("preco_cents", 0))
    if cupom and cupom.tipo == "frete":
        frete_cents = 0
    total = tot["subtotal_cents"] - desconto + frete_cents
    pedido = Pedido(
        numero=_proximo_numero(db),
        cliente_id=cliente.id,
        status=StatusPedido.AGUARDANDO,
        subtotal_cents=tot["subtotal_cents"],
        frete_cents=frete_cents,
        desconto_cents=desconto,
        total_cents=total,
        cupom=cupom.codigo if cupom else "",
        frete_metodo=frete_opcao.get("metodo", ""),
        frete_prazo_dias=int(frete_opcao.get("prazo_dias", 0)),
        token=token_url(18),
        nome=cliente.nome,
        email=cliente.email,
        telefone=cliente.telefone,
        cpf=cliente.cpf,
        cep=cliente.cep,
        logradouro=cliente.logradouro,
        numero_end=cliente.numero,
        complemento=cliente.complemento,
        bairro=cliente.bairro,
        cidade=cliente.cidade,
        uf=cliente.uf,
        peso_g=tot["peso_g"],
        observacoes_cliente=(dados.get("observacoes") or "")[:500],
        origem=origem,
    )
    db.add(pedido)
    db.flush()
    for l in linhas:
        p = l["produto"]
        db.add(PedidoItem(pedido_id=pedido.id, produto_id=p.id, sku=p.sku, nome=p.nome, quantidade=l["quantidade"], preco_unit_cents=p.preco_cents, custo_unit_cents=p.custo_cents))
    if cupom:
        cupom.usos += 1
    txid, payload = pagamentos.gerar_para_pedido(db, pedido.numero, total)
    pedido.pix_txid = txid
    pedido.pix_payload = payload
    db.add(Pagamento(pedido_id=pedido.id, metodo="pix", valor_cents=total, status="pendente", provedor="manual", referencia=txid))
    db.flush()
    notificacoes.registrar(db, pedido, "pedido_criado")
    return pedido


# ---------------------------------------------------------------- transições
def confirmar_pagamento(db: Session, pedido: Pedido, provedor: str = "manual", referencia: str = "") -> None:
    if pedido.status != StatusPedido.AGUARDANDO:
        raise ErroPedido(f"Pedido {pedido.numero} não está aguardando pagamento.")
    # Baixa o estoque agora (até aqui era só reserva lógica).
    for item in pedido.itens:
        if item.produto is None:
            continue
        estoque.movimentar(db, item.produto, -item.quantidade, TipoMovimento.VENDA, ref_tipo="pedido", ref_id=pedido.id, observacao=f"Pedido {pedido.numero}")
    pagamento = next((pg for pg in pedido.pagamentos if pg.status == "pendente"), None)
    if pagamento is None:
        pagamento = Pagamento(pedido_id=pedido.id, metodo=pedido.pagamento_metodo, valor_cents=pedido.total_cents)
        db.add(pagamento)
    pagamento.status = "confirmado"
    pagamento.provedor = provedor
    pagamento.referencia = referencia or pagamento.referencia
    pagamento.confirmado_em = agora()
    caixa.lancar(db, "entrada", "venda", pedido.total_cents, f"Pedido {pedido.numero} — {pedido.nome}", ref_tipo="pedido", ref_id=pedido.id)
    pedido.status = StatusPedido.PAGO
    pedido.pago_em = agora()
    pedido.cliente_informou_pagamento = False
    db.flush()
    notificacoes.registrar(db, pedido, "pago")
    if configuracoes.obter_bool(db, "nfe_auto_emitir"):
        from . import faturamento  # import tardio: evita ciclo

        try:
            faturamento.emitir(db, pedido)
        except Exception as exc:  # a emissão não pode travar a venda
            pedido.observacoes = (pedido.observacoes + f"\n[NF-e] falhou ao emitir automaticamente: {exc}").strip()


def marcar_item_separado(db: Session, pedido: Pedido, item_id: int, separado: bool = True) -> None:
    for item in pedido.itens:
        if item.id == item_id:
            item.separado = separado
    db.flush()


def concluir_separacao(db: Session, pedido: Pedido) -> None:
    if pedido.status != StatusPedido.PAGO:
        raise ErroPedido("Só pedidos pagos entram em separação.")
    for item in pedido.itens:
        item.separado = True
    pedido.status = StatusPedido.SEPARADO
    pedido.separado_em = agora()
    db.flush()


def embalar(db: Session, pedido: Pedido, pacote: str = "", peso_g: int | None = None) -> None:
    if pedido.status not in {StatusPedido.PAGO, StatusPedido.SEPARADO}:
        raise ErroPedido("Este pedido não está pronto para embalar.")
    if pedido.status == StatusPedido.PAGO:
        concluir_separacao(db, pedido)
    pedido.pacote = pacote[:40]
    if peso_g:
        pedido.peso_g = int(peso_g)
    pedido.status = StatusPedido.EMBALADO
    pedido.embalado_em = agora()
    db.flush()


def enviar(db: Session, pedido: Pedido, rastreio: str, custo_postagem_cents: int = 0) -> None:
    if pedido.status not in {StatusPedido.SEPARADO, StatusPedido.EMBALADO, StatusPedido.PAGO}:
        raise ErroPedido("Este pedido não está pronto para envio.")
    if pedido.status != StatusPedido.EMBALADO:
        embalar(db, pedido, pedido.pacote)
    pedido.rastreio = (rastreio or "").strip().upper()
    pedido.custo_postagem_cents = int(custo_postagem_cents or 0)
    if pedido.custo_postagem_cents > 0:
        caixa.lancar(db, "saida", "frete", pedido.custo_postagem_cents, f"Postagem pedido {pedido.numero}", ref_tipo="pedido", ref_id=pedido.id)
    pedido.status = StatusPedido.ENVIADO
    pedido.enviado_em = agora()
    db.flush()
    notificacoes.registrar(db, pedido, "enviado")
    prazo = max(pedido.frete_prazo_dias, 1) + 2
    _criar_followup(db, pedido, TipoFollowUp.CONFIRMAR_ENTREGA, hoje() + timedelta(days=prazo))


def entregar(db: Session, pedido: Pedido, avisar: bool = True) -> None:
    if pedido.status != StatusPedido.ENVIADO:
        raise ErroPedido("Só pedidos enviados podem ser marcados como entregues.")
    pedido.status = StatusPedido.ENTREGUE
    pedido.entregue_em = agora()
    for f in pedido.followups:
        if f.tipo == TipoFollowUp.CONFIRMAR_ENTREGA and f.status == "pendente":
            f.status = "feito"
            f.feito_em = agora()
    dias_aval = configuracoes.obter_int(db, "pos_venda_avaliacao_dias", 3)
    dias_cupom = configuracoes.obter_int(db, "pos_venda_cupom_dias", 30)
    _criar_followup(db, pedido, TipoFollowUp.PEDIR_AVALIACAO, hoje() + timedelta(days=dias_aval))
    _criar_followup(db, pedido, TipoFollowUp.CUPOM_RETORNO, hoje() + timedelta(days=dias_cupom))
    db.flush()
    if avisar:
        notificacoes.registrar(db, pedido, "entregue")


def cancelar(db: Session, pedido: Pedido, motivo: str = "", estornar: bool = True, avisar: bool = True) -> None:
    if pedido.status in {StatusPedido.CANCELADO, StatusPedido.DEVOLVIDO}:
        return
    if pedido.status in {StatusPedido.ENVIADO, StatusPedido.ENTREGUE}:
        raise ErroPedido("Pedido já enviado: trate como devolução no pós-venda.")
    estava_pago = pedido.pago
    if estava_pago:
        for item in pedido.itens:
            if item.produto is not None:
                estoque.movimentar(db, item.produto, item.quantidade, TipoMovimento.CANCELAMENTO, ref_tipo="pedido", ref_id=pedido.id, observacao=f"Cancelamento {pedido.numero}")
        if estornar:
            caixa.lancar(db, "saida", "estorno", pedido.total_cents, f"Estorno pedido {pedido.numero}", ref_tipo="pedido", ref_id=pedido.id)
            for pg in pedido.pagamentos:
                if pg.status == "confirmado":
                    pg.status = "estornado"
        nota = pedido.nota_atual
        if nota and nota.status == StatusNota.AUTORIZADA:
            from . import faturamento

            try:
                faturamento.cancelar(db, nota, f"Cancelamento do pedido {pedido.numero}: {motivo or 'a pedido'}")
            except Exception as exc:
                pedido.observacoes = (pedido.observacoes + f"\n[NF-e] cancelar manualmente: {exc}").strip()
    else:
        for pg in pedido.pagamentos:
            if pg.status == "pendente":
                pg.status = "cancelado"
    for f in pedido.followups:
        if f.status == "pendente":
            f.status = "pulado"
    pedido.status = StatusPedido.CANCELADO
    pedido.cancelado_em = agora()
    pedido.motivo_cancelamento = (motivo or "")[:200]
    db.flush()
    if avisar and estava_pago:
        notificacoes.registrar(db, pedido, "cancelado")


def registrar_devolucao(db: Session, pedido: Pedido, itens_qtd: dict[int, int], reembolso_cents: int, motivo: str = "") -> None:
    """Mercadoria voltou: entra no estoque, sai o reembolso do caixa."""
    if not pedido.pago:
        raise ErroPedido("Só pedidos pagos têm devolução.")
    algum = False
    for item in pedido.itens:
        qtd = int(itens_qtd.get(item.id, 0))
        if qtd > 0 and item.produto is not None:
            estoque.movimentar(db, item.produto, min(qtd, item.quantidade), TipoMovimento.DEVOLUCAO, ref_tipo="pedido", ref_id=pedido.id, observacao=f"Devolução {pedido.numero}")
            algum = True
    if reembolso_cents > 0:
        caixa.lancar(db, "saida", "estorno", reembolso_cents, f"Reembolso pedido {pedido.numero}", ref_tipo="pedido", ref_id=pedido.id)
    if algum and sum(itens_qtd.values()) >= pedido.quantidade_itens:
        pedido.status = StatusPedido.DEVOLVIDO
    pedido.observacoes = (pedido.observacoes + f"\n[Devolução] {motivo}".rstrip()).strip()
    db.flush()


def cliente_informou_pagamento(db: Session, pedido: Pedido) -> None:
    if pedido.status == StatusPedido.AGUARDANDO:
        pedido.cliente_informou_pagamento = True
        db.flush()


def _criar_followup(db: Session, pedido: Pedido, tipo: str, vence_em: date) -> FollowUp | None:
    existente = db.execute(select(FollowUp).where(FollowUp.pedido_id == pedido.id, FollowUp.tipo == tipo)).scalar_one_or_none()
    if existente:
        return existente
    f = FollowUp(pedido_id=pedido.id, cliente_id=pedido.cliente_id, tipo=tipo, vence_em=vence_em)
    db.add(f)
    db.flush()
    return f


# ----------------------------------------------------------------- consultas
def por_numero(db: Session, numero: str) -> Pedido | None:
    numero = (numero or "").strip().upper()
    if numero and not numero.startswith("P"):
        numero = "P" + numero
    return db.execute(select(Pedido).where(Pedido.numero == numero)).scalar_one_or_none()


def listar(db: Session, status: str | list[str] | None = None, busca: str = "", inicio: date | None = None, fim: date | None = None, limite: int = 300) -> list[Pedido]:
    q = select(Pedido).order_by(Pedido.id.desc()).limit(limite)
    if status:
        q = q.where(Pedido.status.in_(status if isinstance(status, list) else [status]))
    if busca:
        termo = f"%{busca.strip()}%"
        digitos = so_digitos(busca)
        cond = Pedido.numero.ilike(termo) | Pedido.nome.ilike(termo) | Pedido.email.ilike(termo) | Pedido.rastreio.ilike(termo)
        if digitos:
            cond = cond | Pedido.cpf.like(f"%{digitos}%") | Pedido.telefone.like(f"%{digitos}%")
        q = q.where(cond)
    if inicio:
        q = q.where(Pedido.criado_em >= inicio.strftime("%Y-%m-%d 00:00:00"))
    if fim:
        q = q.where(Pedido.criado_em <= fim.strftime("%Y-%m-%d 23:59:59"))
    return list(db.execute(q).scalars())


def contagem_por_status(db: Session) -> dict[str, int]:
    linhas = db.execute(select(Pedido.status, func.count(Pedido.id)).group_by(Pedido.status)).all()
    return {s: int(n) for s, n in linhas}


def lista_separacao(db: Session) -> list[dict]:
    """Tudo que precisa ser pego na prateleira agora, agrupado por produto."""
    pedidos = listar(db, status=StatusPedido.PAGO, limite=500)
    por_produto: dict[int, dict] = {}
    for pedido in pedidos:
        for item in pedido.itens:
            chave = item.produto_id or -item.id
            linha = por_produto.setdefault(chave, {"produto": item.produto, "nome": item.nome, "sku": item.sku, "quantidade": 0, "pedidos": []})
            linha["quantidade"] += item.quantidade
            linha["pedidos"].append(pedido.numero)
    return sorted(por_produto.values(), key=lambda l: ((l["produto"].localizacao if l["produto"] else ""), l["nome"]))
