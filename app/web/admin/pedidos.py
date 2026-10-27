"""Pedidos: fila, detalhe, separação, embalagem, envio, cancelamento, etiquetas e venda manual."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ...config import config
from ...db import get_db
from ...models import Pedido, StatusPedido
from ...security import flash
from ...services import catalogo, clientes as svc_clientes, faturamento, frete, notificacoes, pagamentos, pedidos as svc_pedidos
from ...utils import parse_dinheiro, so_digitos
from ..render import render

router = APIRouter(prefix="/pedidos")


def _pedido(db: Session, pedido_id: int) -> Pedido:
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise ValueError("Pedido não encontrado")
    return pedido


@router.get("")
def lista(request: Request, status: str = "", q: str = "", db: Session = Depends(get_db)):
    filtro = None
    if status == "abertos":
        filtro = StatusPedido.ABERTOS
    elif status == "nao_enviados":
        filtro = StatusPedido.PAGOS_NAO_ENVIADOS
    elif status:
        filtro = status
    pedidos = svc_pedidos.listar(db, status=filtro, busca=q)
    return render(request, "admin/pedidos.html", db, pedidos=pedidos, status=status, q=q, contagem=svc_pedidos.contagem_por_status(db))


@router.get("/separacao")
def separacao(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/separacao.html", db, linhas=svc_pedidos.lista_separacao(db), pedidos=svc_pedidos.listar(db, status=StatusPedido.PAGO))


@router.get("/novo")
def novo(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/pedido_novo.html", db, produtos=catalogo.produtos(db), erros={}, dados={})


@router.post("/novo")
async def novo_enviar(request: Request, db: Session = Depends(get_db)):
    """Venda manual (WhatsApp/Instagram): mesmo fluxo do site, mas digitada pela loja."""
    form = await request.form()
    dados = {k: (form.get(k) or "").strip() for k in ("nome", "email", "telefone", "cpf", "nascimento", "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "observacoes", "cupom", "frete_metodo", "frete_valor")}
    dados["consentimento_lgpd"] = True
    dados["maior_de_idade"] = True
    carrinho: dict[str, int] = {}
    for chave, valor in form.multi_items():
        if chave.startswith("qtd_") and valor and int(valor) > 0:
            carrinho[chave[4:]] = int(valor)
    linhas = svc_pedidos.itens_do_carrinho(db, carrinho)
    erros = svc_clientes.validar_kyc(dados)
    if not linhas:
        erros["carrinho"] = "Escolha pelo menos um produto."
    if erros:
        return render(request, "admin/pedido_novo.html", db, status_code=400, produtos=catalogo.produtos(db), erros=erros, dados=dados)
    totais = svc_pedidos.totais_carrinho(linhas)
    if dados["frete_metodo"] == "retirada":
        opcao = {"metodo": "Retirada", "preco_cents": 0, "prazo_dias": 0}
    elif dados["frete_valor"]:
        opcao = {"metodo": dados["frete_metodo"] or "PAC", "preco_cents": parse_dinheiro(dados["frete_valor"]), "prazo_dias": 7}
    else:
        cot = frete.cotar(db, dados["cep"], totais["subtotal_cents"], totais["peso_g"])
        opcao = next((o for o in cot.get("opcoes", []) if o["metodo"] == dados["frete_metodo"]), cot["opcoes"][0] if cot.get("opcoes") else {"metodo": "PAC", "preco_cents": 0, "prazo_dias": 7})
    try:
        cliente = svc_clientes.obter_ou_criar(db, dados)
        pedido = svc_pedidos.criar(db, linhas, cliente, dados, opcao, cupom_codigo=dados["cupom"], origem="manual")
        db.commit()
    except svc_pedidos.ErroPedido as exc:
        db.rollback()
        erros["carrinho"] = str(exc)
        return render(request, "admin/pedido_novo.html", db, status_code=400, produtos=catalogo.produtos(db), erros=erros, dados=dados)
    flash(request, f"Pedido {pedido.numero} criado. Mande o link de pagamento para o cliente.")
    return RedirectResponse(f"/admin/pedidos/{pedido.id}", status_code=303)


@router.get("/{pedido_id}")
def detalhe(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    qr = pagamentos.qr_svg_data_uri(pedido.pix_payload) if pedido.pix_payload and pedido.status == StatusPedido.AGUARDANDO else ""
    return render(
        request, "admin/pedido.html", db, pedido=pedido, qr=qr,
        notificacoes=notificacoes.do_pedido(db, pedido.id), rastreio_url=frete.url_rastreio(pedido.rastreio),
        link_pagamento=f"{config.BASE_URL}/pedido/{pedido.numero}/pagamento?t={pedido.token}",
        link_whatsapp_pagamento=notificacoes.link_whatsapp(pedido.telefone, notificacoes.textos(db, pedido, "pedido_criado")[1]),
        resumo_cliente=svc_clientes.resumo_cliente(db, pedido.cliente) if pedido.cliente else None,
    )


@router.post("/{pedido_id}/confirmar-pagamento")
async def confirmar_pagamento(request: Request, pedido_id: int, referencia: str = Form(""), db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        svc_pedidos.confirmar_pagamento(db, pedido, provedor="manual", referencia=referencia)
        db.commit()
        flash(request, f"Pagamento do {pedido.numero} confirmado. Estoque baixado, pedido na fila de separação.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.post("/{pedido_id}/separar-item")
async def separar_item(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    corpo = await request.json()
    pedido = _pedido(db, pedido_id)
    svc_pedidos.marcar_item_separado(db, pedido, int(corpo.get("item_id")), bool(corpo.get("separado", True)))
    db.commit()
    return JSONResponse({"ok": True, "todos": pedido.todos_separados})


@router.post("/{pedido_id}/concluir-separacao")
async def concluir_separacao(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        svc_pedidos.concluir_separacao(db, pedido)
        db.commit()
        flash(request, f"{pedido.numero} separado. Agora é embalar.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.post("/{pedido_id}/embalar")
async def embalar(request: Request, pedido_id: int, pacote: str = Form(""), peso_g: str = Form(""), db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        svc_pedidos.embalar(db, pedido, pacote, int(so_digitos(peso_g) or 0) or None)
        db.commit()
        flash(request, f"{pedido.numero} embalado. Imprima a etiqueta e poste nos Correios.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.post("/{pedido_id}/enviar")
async def enviar(request: Request, pedido_id: int, rastreio: str = Form(""), custo_postagem: str = Form(""), db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        svc_pedidos.enviar(db, pedido, rastreio, parse_dinheiro(custo_postagem))
        db.commit()
        flash(request, f"{pedido.numero} enviado. Mensagem com o rastreio pronta para o cliente.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.post("/{pedido_id}/entregar")
async def entregar(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        svc_pedidos.entregar(db, pedido)
        db.commit()
        flash(request, f"{pedido.numero} entregue. Pós-venda agendado.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.post("/{pedido_id}/cancelar")
async def cancelar(request: Request, pedido_id: int, motivo: str = Form(""), estornar: str = Form("1"), db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        svc_pedidos.cancelar(db, pedido, motivo=motivo, estornar=estornar == "1")
        db.commit()
        flash(request, f"{pedido.numero} cancelado.")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.post("/{pedido_id}/observacao")
async def observacao(request: Request, pedido_id: int, observacoes: str = Form(""), db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    pedido.observacoes = observacoes.strip()
    db.commit()
    return RedirectResponse(f"/admin/pedidos/{pedido_id}", status_code=303)


@router.post("/{pedido_id}/nfe")
async def emitir_nfe(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    try:
        nota = faturamento.emitir(db, pedido)
        db.commit()
        if nota.status == "autorizada":
            flash(request, f"NF-e {nota.numero} autorizada.")
        elif nota.status == "processando":
            flash(request, f"NF-e {nota.numero} enviada ao emissor. Consulte o status em instantes.", "aviso")
        else:
            flash(request, f"NF-e {nota.numero} com erro: {nota.mensagem}", "erro")
    except Exception as exc:
        db.rollback()
        flash(request, str(exc), "erro")
    return RedirectResponse(_voltar(request, f"/admin/pedidos/{pedido_id}"), status_code=303)


@router.get("/{pedido_id}/etiqueta")
def etiqueta(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    return render(request, "impressao/etiqueta.html", db, pedido=pedido)


@router.get("/{pedido_id}/declaracao")
def declaracao(request: Request, pedido_id: int, db: Session = Depends(get_db)):
    pedido = _pedido(db, pedido_id)
    return render(request, "impressao/declaracao.html", db, pedido=pedido)


def _voltar(request: Request, padrao: str) -> str:
    destino = request.headers.get("referer") or ""
    if "/admin" in destino and "/etiqueta" not in destino:
        return destino
    return padrao
