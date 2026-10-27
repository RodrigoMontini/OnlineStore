"""Clientes e KYC: quem compra, se é maior de idade, se os dados batem."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Cliente, Pedido, StatusPedido
from ..utils import agora, cpf_valido, email_valido, idade, so_digitos


def validar_kyc(dados: dict) -> dict[str, str]:
    """Valida os dados do checkout. Retorna {campo: mensagem} (vazio = ok)."""
    erros: dict[str, str] = {}
    nome = (dados.get("nome") or "").strip()
    if len(nome.split()) < 2:
        erros["nome"] = "Informe nome e sobrenome."
    if not email_valido(dados.get("email")):
        erros["email"] = "E-mail inválido."
    tel = so_digitos(dados.get("telefone"))
    if len(tel) not in (10, 11):
        erros["telefone"] = "Telefone com DDD (10 ou 11 dígitos)."
    if not cpf_valido(dados.get("cpf")):
        erros["cpf"] = "CPF inválido."
    nasc = dados.get("nascimento")
    if isinstance(nasc, str):
        try:
            nasc = date.fromisoformat(nasc)
        except ValueError:
            nasc = None
    if not nasc:
        erros["nascimento"] = "Informe a data de nascimento."
    else:
        anos = idade(nasc)
        if anos is None or anos < 18:
            erros["nascimento"] = "A compra é permitida só para maiores de 18 anos."
        elif anos > 110:
            erros["nascimento"] = "Confira a data de nascimento."
    if not dados.get("consentimento_lgpd"):
        erros["consentimento_lgpd"] = "Precisamos do seu consentimento para processar o pedido."
    if not dados.get("maior_de_idade"):
        erros["maior_de_idade"] = "Confirme que você tem 18 anos ou mais."
    if len(so_digitos(dados.get("cep"))) != 8:
        erros["cep"] = "CEP com 8 dígitos."
    for campo, rotulo in (("logradouro", "endereço"), ("numero", "número"), ("bairro", "bairro"), ("cidade", "cidade")):
        if not (dados.get(campo) or "").strip():
            erros[campo] = f"Informe o {rotulo}."
    if len((dados.get("uf") or "").strip()) != 2:
        erros["uf"] = "UF."
    return erros


def obter_ou_criar(db: Session, dados: dict) -> Cliente:
    cpf = so_digitos(dados.get("cpf"))
    email = (dados.get("email") or "").strip().lower()
    cliente = None
    if cpf:
        cliente = db.execute(select(Cliente).where(Cliente.cpf == cpf)).scalar_one_or_none()
    if cliente is None and email:
        cliente = db.execute(select(Cliente).where(Cliente.email == email)).scalar_one_or_none()
    if cliente is None:
        cliente = Cliente(nome="", email=email)
        db.add(cliente)
    nasc = dados.get("nascimento")
    if isinstance(nasc, str):
        try:
            nasc = date.fromisoformat(nasc)
        except ValueError:
            nasc = None
    cliente.nome = (dados.get("nome") or "").strip()
    cliente.email = email
    cliente.telefone = so_digitos(dados.get("telefone"))
    cliente.cpf = cpf
    cliente.nascimento = nasc or cliente.nascimento
    cliente.consentimento_lgpd = bool(dados.get("consentimento_lgpd")) or cliente.consentimento_lgpd
    cliente.aceita_marketing = bool(dados.get("aceita_marketing"))
    cliente.maior_de_idade_confirmado = bool(dados.get("maior_de_idade")) or cliente.maior_de_idade_confirmado
    cliente.cep = so_digitos(dados.get("cep"))
    cliente.logradouro = (dados.get("logradouro") or "").strip()
    cliente.numero = (dados.get("numero") or "").strip()
    cliente.complemento = (dados.get("complemento") or "").strip()
    cliente.bairro = (dados.get("bairro") or "").strip()
    cliente.cidade = (dados.get("cidade") or "").strip()
    cliente.uf = (dados.get("uf") or "").strip().upper()[:2]
    db.flush()
    return cliente


def kyc_flags(cliente: Cliente) -> dict[str, bool]:
    anos = idade(cliente.nascimento)
    return {
        "cpf_valido": cpf_valido(cliente.cpf),
        "maior_de_idade": anos is not None and anos >= 18,
        "email_valido": email_valido(cliente.email),
        "telefone_ok": len(so_digitos(cliente.telefone)) in (10, 11),
        "consentimento": cliente.consentimento_lgpd,
        "endereco_ok": bool(cliente.cep and cliente.logradouro and cliente.cidade and cliente.uf),
    }


def kyc_completo(cliente: Cliente) -> bool:
    return all(kyc_flags(cliente).values())


def resumo_cliente(db: Session, cliente: Cliente) -> dict:
    pedidos_pagos = [p for p in cliente.pedidos if p.status in StatusPedido.PAGOS]
    total = sum(p.total_cents for p in pedidos_pagos)
    ultimo = max((p.pago_em for p in pedidos_pagos if p.pago_em), default=None)
    primeiro = min((p.pago_em for p in pedidos_pagos if p.pago_em), default=None)
    return {
        "pedidos": len(cliente.pedidos),
        "pedidos_pagos": len(pedidos_pagos),
        "ltv_cents": total,
        "ticket_medio_cents": int(total / len(pedidos_pagos)) if pedidos_pagos else 0,
        "ultimo_pedido": ultimo,
        "primeiro_pedido": primeiro,
        "recorrente": len(pedidos_pagos) >= 2,
        "kyc": kyc_flags(cliente),
        "kyc_ok": kyc_completo(cliente),
        "idade": idade(cliente.nascimento),
        "dias_sem_comprar": (agora() - ultimo).days if ultimo else None,
    }


def listar(db: Session, busca: str = "", limite: int = 300) -> list[Cliente]:
    q = select(Cliente).order_by(Cliente.id.desc()).limit(limite)
    if busca:
        termo = f"%{busca.strip()}%"
        digitos = so_digitos(busca)
        cond = Cliente.nome.ilike(termo) | Cliente.email.ilike(termo)
        if digitos:
            cond = cond | Cliente.cpf.like(f"%{digitos}%") | Cliente.telefone.like(f"%{digitos}%")
        q = q.where(cond)
    return list(db.execute(q).scalars())


def insights(db: Session) -> dict:
    """Visão 'conheça seu cliente' para o relatório."""
    clientes = list(db.execute(select(Cliente)).scalars())
    desde_30 = agora() - timedelta(days=30)
    novos_30d = sum(1 for c in clientes if c.criado_em and c.criado_em >= desde_30)
    linhas = []
    for c in clientes:
        r = resumo_cliente(db, c)
        linhas.append({"cliente": c, **r})
    compradores = [l for l in linhas if l["pedidos_pagos"] > 0]
    recorrentes = [l for l in compradores if l["recorrente"]]
    kyc_incompleto = [l for l in linhas if not l["kyc_ok"]]
    por_uf: dict[str, int] = {}
    for l in compradores:
        por_uf[l["cliente"].uf or "?"] = por_uf.get(l["cliente"].uf or "?", 0) + 1
    inativos = [l for l in compradores if l["dias_sem_comprar"] is not None and l["dias_sem_comprar"] > 60]
    top = sorted(compradores, key=lambda l: l["ltv_cents"], reverse=True)[:10]
    ltv_total = sum(l["ltv_cents"] for l in compradores)
    return {
        "total": len(clientes),
        "novos_30d": novos_30d,
        "compradores": len(compradores),
        "recorrentes": len(recorrentes),
        "taxa_recorrencia": round(100.0 * len(recorrentes) / len(compradores), 1) if compradores else 0.0,
        "ltv_medio_cents": int(ltv_total / len(compradores)) if compradores else 0,
        "kyc_incompleto": kyc_incompleto,
        "por_uf": sorted(por_uf.items(), key=lambda kv: kv[1], reverse=True),
        "inativos_60d": inativos,
        "top": top,
        "aceitam_marketing": sum(1 for c in clientes if c.aceita_marketing),
        "linhas": sorted(linhas, key=lambda l: l["ltv_cents"], reverse=True),
    }
