"""Pós-venda: follow-ups automáticos, tickets (dúvida/troca/devolução) e avaliações."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Avaliacao, Cliente, FollowUp, Pedido, Produto, Ticket, TicketMensagem, TipoTicket
from ..utils import agora, hoje
from . import notificacoes, pedidos as svc_pedidos


# ---------------------------------------------------------------- follow-ups
def followups_pendentes(db: Session, ate=None, limite: int = 200) -> list[FollowUp]:
    ate = ate or hoje()
    return list(
        db.execute(
            select(FollowUp).where(FollowUp.status == "pendente", FollowUp.vence_em <= ate).order_by(FollowUp.vence_em, FollowUp.id).limit(limite)
        ).scalars()
    )


def followups_futuros(db: Session, limite: int = 100) -> list[FollowUp]:
    return list(db.execute(select(FollowUp).where(FollowUp.status == "pendente", FollowUp.vence_em > hoje()).order_by(FollowUp.vence_em).limit(limite)).scalars())


def preparar_mensagem(db: Session, followup: FollowUp) -> dict:
    """Texto e link de WhatsApp prontos para o follow-up."""
    pedido = followup.pedido
    if not pedido:
        return {"assunto": followup.label, "texto": "", "link": ""}
    assunto, texto = notificacoes.textos(db, pedido, followup.tipo)
    return {"assunto": assunto, "texto": texto, "link": notificacoes.link_whatsapp(pedido.telefone, texto)}


def concluir_followup(db: Session, followup: FollowUp, observacao: str = "", registrar_notificacao: bool = True) -> None:
    followup.status = "feito"
    followup.feito_em = agora()
    followup.observacao = observacao[:200]
    if followup.pedido and registrar_notificacao:
        notificacoes.registrar(db, followup.pedido, followup.tipo, enviar_email=True)
    db.flush()


def pular_followup(db: Session, followup: FollowUp) -> None:
    followup.status = "pulado"
    followup.feito_em = agora()
    db.flush()


def adiar_followup(db: Session, followup: FollowUp, dias: int = 2) -> None:
    followup.vence_em = hoje() + timedelta(days=dias)
    db.flush()


# -------------------------------------------------------------------- tickets
def abrir_ticket(db: Session, tipo: str, assunto: str, mensagem: str, nome: str = "", email: str = "", telefone: str = "", pedido: Pedido | None = None, cliente: Cliente | None = None, autor: str = "cliente") -> Ticket:
    if tipo not in TipoTicket.LABELS:
        tipo = TipoTicket.DUVIDA
    if pedido and not cliente:
        cliente = pedido.cliente
    t = Ticket(
        tipo=tipo,
        assunto=assunto[:200] or TipoTicket.LABELS[tipo],
        nome=(nome or (cliente.nome if cliente else "") or (pedido.nome if pedido else ""))[:160],
        email=(email or (cliente.email if cliente else "") or (pedido.email if pedido else ""))[:200],
        telefone=(telefone or (cliente.telefone if cliente else "") or (pedido.telefone if pedido else ""))[:30],
        pedido_id=pedido.id if pedido else None,
        cliente_id=cliente.id if cliente else None,
    )
    db.add(t)
    db.flush()
    if mensagem.strip():
        db.add(TicketMensagem(ticket_id=t.id, autor=autor, texto=mensagem.strip()))
    db.flush()
    return t


def responder(db: Session, ticket: Ticket, texto: str, autor: str = "loja") -> TicketMensagem:
    m = TicketMensagem(ticket_id=ticket.id, autor=autor, texto=texto.strip())
    db.add(m)
    if ticket.status == "aberto" and autor == "loja":
        ticket.status = "em_andamento"
    db.flush()
    return m


def link_whatsapp_resposta(ticket: Ticket, texto: str) -> str:
    return notificacoes.link_whatsapp(ticket.telefone, texto)


def resolver(db: Session, ticket: Ticket) -> None:
    ticket.status = "resolvido"
    ticket.resolvido_em = agora()
    db.flush()


def reabrir(db: Session, ticket: Ticket) -> None:
    ticket.status = "aberto"
    ticket.resolvido_em = None
    db.flush()


def tickets(db: Session, status: str | None = None, limite: int = 200) -> list[Ticket]:
    q = select(Ticket).order_by(Ticket.id.desc()).limit(limite)
    if status == "abertos":
        q = q.where(Ticket.status.in_(["aberto", "em_andamento"]))
    elif status:
        q = q.where(Ticket.status == status)
    return list(db.execute(q).scalars())


def concluir_devolucao(db: Session, ticket: Ticket, itens_qtd: dict[int, int], reembolso_cents: int, motivo: str = "") -> None:
    if not ticket.pedido:
        raise ValueError("Ticket sem pedido vinculado.")
    svc_pedidos.registrar_devolucao(db, ticket.pedido, itens_qtd, reembolso_cents, motivo or ticket.assunto)
    responder(db, ticket, f"Devolução registrada: reembolso de R$ {reembolso_cents / 100:.2f}. {motivo}".strip(), autor="loja")
    resolver(db, ticket)


# ----------------------------------------------------------------- avaliações
def pedido_por_token(db: Session, token: str) -> Pedido | None:
    if not token:
        return None
    return db.execute(select(Pedido).where(Pedido.token == token)).scalar_one_or_none()


def salvar_avaliacao(db: Session, pedido: Pedido, produto: Produto, nota: int, comentario: str, nome_exibicao: str = "") -> Avaliacao:
    if not any(i.produto_id == produto.id for i in pedido.itens):
        raise ValueError("Este produto não está no pedido.")
    existente = db.execute(select(Avaliacao).where(Avaliacao.pedido_id == pedido.id, Avaliacao.produto_id == produto.id)).scalar_one_or_none()
    if existente:
        existente.nota = nota
        existente.comentario = comentario
        existente.nome_exibicao = nome_exibicao
        db.flush()
        return existente
    a = Avaliacao(
        produto_id=produto.id, pedido_id=pedido.id, cliente_id=pedido.cliente_id, nota=max(1, min(5, int(nota))),
        comentario=comentario.strip()[:1000], nome_exibicao=(nome_exibicao or (pedido.nome.split(" ")[0] if pedido.nome else "Cliente"))[:60],
    )
    db.add(a)
    db.flush()
    return a


def avaliacoes_pendentes(db: Session) -> list[Avaliacao]:
    return list(db.execute(select(Avaliacao).where(Avaliacao.aprovada.is_(False)).order_by(Avaliacao.id.desc())).scalars())


def avaliacoes_aprovadas(db: Session, produto_id: int | None = None, limite: int = 12) -> list[Avaliacao]:
    q = select(Avaliacao).where(Avaliacao.aprovada.is_(True)).order_by(Avaliacao.id.desc()).limit(limite)
    if produto_id:
        q = q.where(Avaliacao.produto_id == produto_id)
    return list(db.execute(q).scalars())
