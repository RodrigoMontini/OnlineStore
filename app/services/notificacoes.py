"""Mensagens ao cliente em cada etapa.

Cada evento vira duas notificações: um link de WhatsApp pronto (um toque no
painel abre a conversa com o texto) e um e-mail (enviado pelo SMTP, se houver;
senão fica na caixa de saída para copiar).
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import config
from ..models import Notificacao, Pedido
from ..utils import agora, brl, telefone_whatsapp
from . import configuracoes, frete


def link_whatsapp(telefone: str, texto: str) -> str:
    numero = telefone_whatsapp(telefone)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(texto)}"


def _url_pedido(pedido: Pedido) -> str:
    return f"{config.BASE_URL}/pedido/{pedido.numero}?t={pedido.token}"


def textos(db: Session, pedido: Pedido, evento: str) -> tuple[str, str]:
    """(assunto, texto) para o evento."""
    loja = configuracoes.obter(db, "loja_nome")
    primeiro_nome = (pedido.nome or "").split(" ")[0]
    url = _url_pedido(pedido)
    if evento == "pedido_criado":
        return (
            f"Pedido {pedido.numero} recebido — falta só o PIX",
            f"Oi, {primeiro_nome}! Recebemos seu pedido {pedido.numero} na {loja} ({brl(pedido.total_cents)}). "
            f"Para a gente separar, é só pagar o PIX nesta página: {url}\n"
            f"Assim que o pagamento entrar, seu pedido vai para separação. Embalagem discreta, sem nome da loja por fora.",
        )
    if evento == "pago":
        return (
            f"Pagamento confirmado — pedido {pedido.numero}",
            f"{primeiro_nome}, pagamento confirmado! Seu pedido {pedido.numero} já está na fila de separação. "
            f"Aviso com o código de rastreio assim que postar. Acompanhe aqui: {url}",
        )
    if evento == "enviado":
        rastreio = pedido.rastreio or "(código a caminho)"
        link = frete.url_rastreio(pedido.rastreio) if pedido.rastreio else url
        return (
            f"Seu pedido {pedido.numero} foi postado",
            f"{primeiro_nome}, seu pedido {pedido.numero} foi postado nos Correios ({pedido.frete_metodo or 'envio'}). "
            f"Código de rastreio: {rastreio}\nAcompanhe: {link}\nPrevisão: até {pedido.frete_prazo_dias or '-'} dias úteis.",
        )
    if evento == "entregue":
        return (
            f"Pedido {pedido.numero} entregue",
            f"{primeiro_nome}, os Correios marcaram seu pedido {pedido.numero} como entregue. Chegou tudo certinho? "
            f"Qualquer coisa, é só responder aqui.",
        )
    if evento == "confirmar_entrega":
        return (
            f"Chegou? Pedido {pedido.numero}",
            f"Oi, {primeiro_nome}! Passando para saber se o pedido {pedido.numero} já chegou e se estava tudo certo. "
            f"Se precisar de qualquer ajuste, me fala por aqui.",
        )
    if evento == "pedir_avaliacao":
        return (
            f"Como foi? Conta pra gente — pedido {pedido.numero}",
            f"{primeiro_nome}, já deu tempo de testar? Uma avaliação sincera ajuda muito outras pessoas a escolherem bem. "
            f"Leva um minuto: {config.BASE_URL}/avaliar/{pedido.token}",
        )
    if evento == "cupom_retorno":
        cupom = configuracoes.obter(db, "cupom_retorno_codigo") or "VOLTA10"
        return (
            f"Um presente para a próxima — {loja}",
            f"{primeiro_nome}, obrigado por comprar com a gente. Na próxima compra, use o cupom {cupom} "
            f"em {config.BASE_URL}/produtos. Vale para você.",
        )
    if evento == "cancelado":
        return (
            f"Pedido {pedido.numero} cancelado",
            f"{primeiro_nome}, o pedido {pedido.numero} foi cancelado"
            + (f" ({pedido.motivo_cancelamento})" if pedido.motivo_cancelamento else "")
            + ". Se você já tinha pago, o estorno é feito pelo mesmo PIX em até 2 dias úteis. Qualquer dúvida, responde aqui.",
        )
    return (f"Pedido {pedido.numero}", f"Atualização do seu pedido {pedido.numero}: {pedido.label_cliente}. {url}")


def registrar(db: Session, pedido: Pedido, evento: str, enviar_email: bool = True) -> list[Notificacao]:
    assunto, texto = textos(db, pedido, evento)
    criadas: list[Notificacao] = []
    if pedido.telefone:
        n = Notificacao(
            pedido_id=pedido.id, cliente_id=pedido.cliente_id, evento=evento, canal="whatsapp",
            destinatario=pedido.telefone, assunto=assunto, texto=texto, link=link_whatsapp(pedido.telefone, texto),
        )
        db.add(n)
        criadas.append(n)
    if pedido.email and enviar_email:
        n = Notificacao(
            pedido_id=pedido.id, cliente_id=pedido.cliente_id, evento=evento, canal="email",
            destinatario=pedido.email, assunto=assunto, texto=texto,
        )
        db.add(n)
        criadas.append(n)
        _tentar_enviar_email(n)
    db.flush()
    return criadas


def _tentar_enviar_email(n: Notificacao) -> None:
    if not (config.SMTP_HOST and config.SMTP_FROM):
        return  # fica pendente na caixa de saída
    try:
        msg = EmailMessage()
        msg["Subject"] = n.assunto
        msg["From"] = config.SMTP_FROM
        msg["To"] = n.destinatario
        msg.set_content(n.texto)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        n.status = "enviada"
        n.enviada_em = agora()
    except Exception as exc:  # pragma: no cover - depende de rede
        n.status = "falhou"
        n.erro = str(exc)[:300]


def marcar_enviada(db: Session, notificacao: Notificacao) -> None:
    notificacao.status = "enviada"
    notificacao.enviada_em = agora()
    db.flush()


def pendentes(db: Session, limite: int = 100) -> list[Notificacao]:
    return list(db.execute(select(Notificacao).where(Notificacao.status == "pendente").order_by(Notificacao.id.desc()).limit(limite)).scalars())


def do_pedido(db: Session, pedido_id: int) -> list[Notificacao]:
    return list(db.execute(select(Notificacao).where(Notificacao.pedido_id == pedido_id).order_by(Notificacao.id.desc())).scalars())
