"""Vitrine: catálogo, carrinho, checkout, pagamento PIX, acompanhamento, avaliação e contato."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Produto, StatusPedido
from ..security import flash, verificar_csrf
from ..services import catalogo, clientes as svc_clientes, configuracoes, frete, pagamentos, pedidos as svc_pedidos, posvenda
from ..utils import so_digitos
from .render import render

router = APIRouter()


# ------------------------------------------------------------------ catálogo
@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return render(
        request, "loja/home.html", db,
        destaques=catalogo.destaques(db, 8),
        categorias=catalogo.categorias(db),
        avaliacoes=posvenda.avaliacoes_aprovadas(db, limite=6),
    )


@router.get("/produtos")
def produtos(request: Request, q: str = "", categoria: str = "", ordem: str = "destaque", db: Session = Depends(get_db)):
    lista = catalogo.produtos(db, categoria_slug=categoria or None, busca=q, ordem=ordem)
    cat_atual = next((c for c in catalogo.categorias(db) if c.slug == categoria), None)
    return render(request, "loja/produtos.html", db, produtos=lista, q=q, categoria=categoria, categoria_atual=cat_atual, ordem=ordem)


@router.get("/categoria/{slug}")
def categoria(slug: str):
    return RedirectResponse(f"/produtos?categoria={slug}", status_code=302)


@router.get("/produto/{slug}")
def produto(request: Request, slug: str, db: Session = Depends(get_db)):
    p = catalogo.por_slug(db, slug)
    if not p or not p.ativo:
        return render(request, "loja/404.html", db, status_code=404)
    media, total = catalogo.media_avaliacoes(db, p.id)
    return render(
        request, "loja/produto.html", db, produto=p, relacionados=catalogo.relacionados(db, p),
        avaliacoes=posvenda.avaliacoes_aprovadas(db, p.id, 10), media=media, total_avaliacoes=total,
    )


# ------------------------------------------------------------------ carrinho
def _carrinho(request: Request) -> dict[str, int]:
    return dict(request.session.get("carrinho") or {})


def _salvar_carrinho(request: Request, carrinho: dict[str, int]) -> None:
    request.session["carrinho"] = {k: int(v) for k, v in carrinho.items() if int(v) > 0}


@router.get("/carrinho")
def carrinho(request: Request, db: Session = Depends(get_db)):
    linhas = svc_pedidos.itens_do_carrinho(db, _carrinho(request))
    totais = svc_pedidos.totais_carrinho(linhas)
    gratis = configuracoes.obter_int(db, "frete_gratis_acima_cents", 0)
    return render(request, "loja/carrinho.html", db, linhas=linhas, totais=totais, frete_gratis_acima=gratis, falta_para_gratis=max(0, gratis - totais["subtotal_cents"]))


@router.post("/carrinho/adicionar", dependencies=[Depends(verificar_csrf)])
async def carrinho_adicionar(request: Request, produto_id: int = Form(...), quantidade: int = Form(1), db: Session = Depends(get_db)):
    p = db.get(Produto, produto_id)
    if not p or not p.ativo:
        flash(request, "Produto indisponível.", "erro")
        return RedirectResponse("/produtos", status_code=303)
    c = _carrinho(request)
    atual = int(c.get(str(produto_id), 0))
    nova = max(1, min(atual + max(1, quantidade), max(p.estoque, 0)))
    if p.estoque <= 0:
        flash(request, f"{p.nome} está esgotado no momento.", "erro")
        return RedirectResponse(f"/produto/{p.slug}", status_code=303)
    c[str(produto_id)] = nova
    _salvar_carrinho(request, c)
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"ok": True, "quantidade": sum(c.values())})
    flash(request, f"{p.nome} está no carrinho.")
    return RedirectResponse("/carrinho", status_code=303)


@router.post("/carrinho/atualizar", dependencies=[Depends(verificar_csrf)])
async def carrinho_atualizar(request: Request, produto_id: int = Form(...), quantidade: int = Form(1)):
    c = _carrinho(request)
    if quantidade <= 0:
        c.pop(str(produto_id), None)
    else:
        c[str(produto_id)] = quantidade
    _salvar_carrinho(request, c)
    return RedirectResponse("/carrinho", status_code=303)


@router.post("/carrinho/remover", dependencies=[Depends(verificar_csrf)])
async def carrinho_remover(request: Request, produto_id: int = Form(...)):
    c = _carrinho(request)
    c.pop(str(produto_id), None)
    _salvar_carrinho(request, c)
    return RedirectResponse("/carrinho", status_code=303)


# ------------------------------------------------------------------ checkout
CAMPOS_CHECKOUT = ["nome", "email", "telefone", "cpf", "nascimento", "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "observacoes", "cupom", "frete_metodo"]


@router.get("/checkout")
def checkout(request: Request, db: Session = Depends(get_db)):
    linhas = svc_pedidos.itens_do_carrinho(db, _carrinho(request))
    if not linhas:
        flash(request, "Seu carrinho está vazio.", "erro")
        return RedirectResponse("/produtos", status_code=303)
    totais = svc_pedidos.totais_carrinho(linhas)
    dados = request.session.get("checkout_dados") or {}
    return render(request, "loja/checkout.html", db, linhas=linhas, totais=totais, dados=dados, erros={}, pix_configurado=bool(configuracoes.obter(db, "pix_chave")))


@router.post("/checkout", dependencies=[Depends(verificar_csrf)])
async def checkout_enviar(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    dados = {campo: (form.get(campo) or "").strip() for campo in CAMPOS_CHECKOUT}
    dados["consentimento_lgpd"] = bool(form.get("consentimento_lgpd"))
    dados["maior_de_idade"] = bool(form.get("maior_de_idade"))
    dados["aceita_marketing"] = bool(form.get("aceita_marketing"))
    linhas = svc_pedidos.itens_do_carrinho(db, _carrinho(request))
    totais = svc_pedidos.totais_carrinho(linhas)
    erros = svc_clientes.validar_kyc(dados)
    cotacao = frete.cotar(db, dados["cep"], totais["subtotal_cents"], totais["peso_g"]) if len(so_digitos(dados["cep"])) == 8 else {"ok": False, "opcoes": []}
    opcao = next((o for o in cotacao.get("opcoes", []) if o["metodo"] == dados["frete_metodo"]), None)
    if not opcao:
        erros["frete_metodo"] = "Escolha a forma de envio."
    if not linhas:
        erros["carrinho"] = "Seu carrinho está vazio."
    cupom_erro = ""
    if dados["cupom"]:
        _, _, cupom_erro = svc_pedidos.aplicar_cupom(db, dados["cupom"], totais["subtotal_cents"])
        if cupom_erro:
            erros["cupom"] = cupom_erro
    request.session["checkout_dados"] = {k: v for k, v in dados.items() if k not in {"cpf", "nascimento"}}
    if erros:
        return render(request, "loja/checkout.html", db, status_code=400, linhas=linhas, totais=totais, dados=dados, erros=erros, pix_configurado=bool(configuracoes.obter(db, "pix_chave")))
    try:
        cliente = svc_clientes.obter_ou_criar(db, dados)
        pedido = svc_pedidos.criar(db, linhas, cliente, dados, opcao, cupom_codigo=dados["cupom"])
        db.commit()
    except svc_pedidos.ErroPedido as exc:
        db.rollback()
        erros["carrinho"] = str(exc)
        return render(request, "loja/checkout.html", db, status_code=400, linhas=linhas, totais=totais, dados=dados, erros=erros, pix_configurado=bool(configuracoes.obter(db, "pix_chave")))
    request.session["carrinho"] = {}
    request.session.pop("checkout_dados", None)
    return RedirectResponse(f"/pedido/{pedido.numero}/pagamento?t={pedido.token}", status_code=303)


# ------------------------------------------------------------------ pedido
def _pedido_do_cliente(db: Session, numero: str, t: str):
    pedido = svc_pedidos.por_numero(db, numero)
    if not pedido or not t or pedido.token != t:
        return None
    return pedido


@router.get("/pedido/{numero}/pagamento")
def pagamento(request: Request, numero: str, t: str = "", db: Session = Depends(get_db)):
    pedido = _pedido_do_cliente(db, numero, t)
    if not pedido:
        return render(request, "loja/404.html", db, status_code=404)
    if pedido.status != StatusPedido.AGUARDANDO:
        return RedirectResponse(f"/pedido/{pedido.numero}?t={t}", status_code=303)
    qr = pagamentos.qr_svg_data_uri(pedido.pix_payload) if pedido.pix_payload else ""
    return render(request, "loja/pagamento.html", db, pedido=pedido, qr=qr, horas_limite=configuracoes.obter_int(db, "cancelar_nao_pago_horas", 24))


@router.post("/pedido/{numero}/paguei", dependencies=[Depends(verificar_csrf)])
async def paguei(request: Request, numero: str, t: str = "", db: Session = Depends(get_db)):
    pedido = _pedido_do_cliente(db, numero, t)
    if pedido:
        svc_pedidos.cliente_informou_pagamento(db, pedido)
        db.commit()
        flash(request, "Obrigado! Vou conferir o PIX e confirmar seu pedido em breve.")
    return RedirectResponse(f"/pedido/{numero}?t={t}", status_code=303)


@router.get("/pedido/{numero}")
def pedido_cliente(request: Request, numero: str, t: str = "", db: Session = Depends(get_db)):
    pedido = _pedido_do_cliente(db, numero, t)
    if not pedido:
        return render(request, "loja/404.html", db, status_code=404)
    return render(request, "loja/pedido.html", db, pedido=pedido, rastreio_url=frete.url_rastreio(pedido.rastreio), etapas=StatusPedido.ORDEM)


@router.get("/acompanhar")
def acompanhar(request: Request, db: Session = Depends(get_db)):
    return render(request, "loja/acompanhar.html", db, erro="")


@router.post("/acompanhar", dependencies=[Depends(verificar_csrf)])
async def acompanhar_buscar(request: Request, numero: str = Form(""), email: str = Form(""), db: Session = Depends(get_db)):
    pedido = svc_pedidos.por_numero(db, numero)
    if pedido and pedido.email.lower() == email.strip().lower():
        return RedirectResponse(f"/pedido/{pedido.numero}?t={pedido.token}", status_code=303)
    return render(request, "loja/acompanhar.html", db, status_code=404, erro="Não achei um pedido com esse número e e-mail.")


# ------------------------------------------------------------------ avaliação
@router.get("/avaliar/{token}")
def avaliar(request: Request, token: str, db: Session = Depends(get_db)):
    pedido = posvenda.pedido_por_token(db, token)
    if not pedido or not pedido.pago:
        return render(request, "loja/404.html", db, status_code=404)
    return render(request, "loja/avaliar.html", db, pedido=pedido, enviado=False)


@router.post("/avaliar/{token}", dependencies=[Depends(verificar_csrf)])
async def avaliar_enviar(request: Request, token: str, db: Session = Depends(get_db)):
    pedido = posvenda.pedido_por_token(db, token)
    if not pedido or not pedido.pago:
        return render(request, "loja/404.html", db, status_code=404)
    form = await request.form()
    nome = (form.get("nome_exibicao") or "").strip()
    for item in pedido.itens:
        nota = form.get(f"nota_{item.id}")
        if nota and item.produto:
            posvenda.salvar_avaliacao(db, pedido, item.produto, int(nota), form.get(f"comentario_{item.id}") or "", nome)
    db.commit()
    return render(request, "loja/avaliar.html", db, pedido=pedido, enviado=True)


# ------------------------------------------------------------------ contato e institucionais
@router.get("/contato")
def contato(request: Request, db: Session = Depends(get_db)):
    return render(request, "loja/contato.html", db, enviado=False, erros={}, dados={})


@router.post("/contato", dependencies=[Depends(verificar_csrf)])
async def contato_enviar(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    dados = {k: (form.get(k) or "").strip() for k in ("nome", "email", "telefone", "tipo", "pedido", "mensagem")}
    erros = {}
    if not dados["nome"]:
        erros["nome"] = "Como posso te chamar?"
    if "@" not in dados["email"]:
        erros["email"] = "E-mail para a resposta."
    if len(dados["mensagem"]) < 5:
        erros["mensagem"] = "Conta o que aconteceu."
    if erros:
        return render(request, "loja/contato.html", db, status_code=400, enviado=False, erros=erros, dados=dados)
    pedido = svc_pedidos.por_numero(db, dados["pedido"]) if dados["pedido"] else None
    if pedido and pedido.email.lower() != dados["email"].lower():
        pedido = None  # não vincula pedido de outra pessoa
    posvenda.abrir_ticket(db, dados["tipo"], f"{dados['tipo'].capitalize()} — {dados['nome']}", dados["mensagem"], nome=dados["nome"], email=dados["email"], telefone=dados["telefone"], pedido=pedido)
    db.commit()
    return render(request, "loja/contato.html", db, enviado=True, erros={}, dados={})


@router.get("/sobre")
def sobre(request: Request, db: Session = Depends(get_db)):
    return render(request, "loja/sobre.html", db)


@router.get("/privacidade")
def privacidade(request: Request, db: Session = Depends(get_db)):
    return render(request, "loja/privacidade.html", db)


@router.get("/trocas")
def trocas(request: Request, db: Session = Depends(get_db)):
    return render(request, "loja/trocas.html", db)


@router.get("/termos")
def termos(request: Request, db: Session = Depends(get_db)):
    return render(request, "loja/termos.html", db)
