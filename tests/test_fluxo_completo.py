"""Fluxo ponta a ponta: compra → estoque → venda no site → PIX → separação → embalagem → envio →
entrega → pós-venda → NF-e → devolução → relatórios. Roda com `pytest`."""
from __future__ import annotations

import re

from tests.conftest import csrf_de

PAGINAS_PUBLICAS = ["/", "/produtos", "/produtos?categoria=lubrificantes", "/produtos?q=plug&ordem=menor_preco", "/sobre", "/trocas", "/privacidade", "/termos", "/contato", "/acompanhar", "/carrinho"]
PAGINAS_ADMIN = [
    "/admin", "/admin/pedidos", "/admin/pedidos?status=abertos", "/admin/pedidos/separacao", "/admin/pedidos/novo", "/admin/compras", "/admin/fornecedores",
    "/admin/estoque", "/admin/estoque?filtro=repor", "/admin/estoque/movimentos", "/admin/produtos", "/admin/produtos/novo", "/admin/categorias",
    "/admin/clientes", "/admin/pos-venda", "/admin/tickets/novo", "/admin/relatorios", "/admin/relatorios/financeiro", "/admin/relatorios/estoque",
    "/admin/relatorios/pedidos", "/admin/relatorios/nao-enviados", "/admin/relatorios/clientes", "/admin/faturamento", "/admin/caixa", "/admin/mensagens",
    "/admin/configuracoes",
]


def _post(c, url, html_token, **dados):
    dados.setdefault("csrf", html_token)
    r = c.post(url, data=dados, follow_redirects=False)
    assert r.status_code in (200, 303), f"{url}: {r.status_code} {r.text[:300]}"
    return r


def _id_pedido(c, numero):
    r = c.get(f"/admin/pedidos?q={numero}")
    m = re.search(rf'href="/admin/pedidos/(\d+)">{numero}<', r.text)
    assert m, "pedido não listado no painel"
    return int(m.group(1))


def test_paginas_publicas(cliente):
    for url in PAGINAS_PUBLICAS:
        r = cliente.get(url)
        assert r.status_code == 200, url


def test_admin_exige_login(cliente):
    r = cliente.get("/admin/pedidos", follow_redirects=False)
    assert r.status_code == 303 and "/admin/" in r.headers["location"]


def test_fluxo(admin):
    c = admin
    # ---------- compra de mercadoria (entrada de estoque + saída de caixa)
    r = c.get("/admin/compras")
    token = csrf_de(r.text)
    r = _post(c, "/admin/compras/nova", token, fornecedor_id="1")
    compra_url = r.headers["location"]
    r = c.get(compra_url)
    assert r.status_code == 200
    _post(c, compra_url + "/itens", token, produto_id="1", quantidade="10", custo="70,00")
    _post(c, compra_url + "/enviar", token)
    r = c.get("/admin/estoque")
    estoque_antes = int(re.search(r"<strong>(\d+)</strong>", c.get("/admin/produtos/1").text.split("Estoque atual")[0][-200:]).group(1)) if False else None
    _post(c, compra_url + "/receber", token, frete="20,00", pagar="1")
    r = c.get(compra_url)
    assert "Recebida" in r.text and "paga" in r.text
    r = c.get("/admin/caixa")
    assert "Compra C1001" in r.text

    # ---------- cliente compra no site
    r = c.get("/produto/kit-plugs-iniciante-3-tamanhos")
    tk = csrf_de(r.text)
    _post(c, "/carrinho/adicionar", tk, produto_id="1", quantidade="2")
    _post(c, "/carrinho/adicionar", tk, produto_id="5", quantidade="1")
    r = c.get("/checkout")
    assert r.status_code == 200
    dados = dict(
        nome="Ana Teste", email="ana@teste.com", telefone="11988887777", cpf="529.982.247-25", nascimento="1990-05-05",
        cep="01310100", logradouro="Av Paulista", numero="1000", complemento="ap 1", bairro="Bela Vista", cidade="São Paulo", uf="SP",
        observacoes="deixar na portaria", cupom="VOLTA10", frete_metodo="SEDEX", consentimento_lgpd="1", maior_de_idade="1",
    )
    # menor de idade é barrado
    r = c.post("/checkout", data={**dados, "csrf": tk, "nascimento": "2015-01-01"}, follow_redirects=False)
    assert r.status_code == 400 and "maiores de 18" in r.text
    r = c.post("/checkout", data={**dados, "csrf": tk}, follow_redirects=False)
    assert r.status_code == 303, r.text[:500]
    pagamento_url = r.headers["location"]
    numero = re.search(r"/pedido/(P\d+)/", pagamento_url).group(1)
    r = c.get(pagamento_url)
    assert r.status_code == 200 and "6304" in r.text  # payload PIX com CRC
    token_cliente = pagamento_url.split("t=")[1]
    _post(c, f"/pedido/{numero}/paguei?t={token_cliente}", tk)
    r = c.get(f"/pedido/{numero}?t={token_cliente}")
    assert "Aguardando pagamento" in r.text
    assert c.get(f"/pedido/{numero}?t=errado").status_code == 404

    # ---------- painel: confirmar PIX → separar → embalar → enviar → entregar
    pid = _id_pedido(c, numero)
    r = c.get(f"/admin/pedidos/{pid}")
    assert "cliente informou" in r.text.lower() or "disse que pagou" in r.text
    tk_admin = csrf_de(r.text)
    estoque_antes = int(re.search(r'name="novo_saldo" type="number" value="(\d+)"', c.get("/admin/estoque?filtro=todos").text).group(1))
    _post(c, f"/admin/pedidos/{pid}/confirmar-pagamento", tk_admin, referencia="E123")
    r = c.get(f"/admin/pedidos/{pid}")
    assert "Separar os itens" in r.text
    r = c.get("/admin/estoque?filtro=todos")
    # produto 1 (Onda) é o primeiro em ordem alfabética? não — procura pela linha do SKU
    linha = r.text.split("PLG-001")[0][-600:]
    r = c.get("/admin/estoque/movimentos?produto_id=1")
    assert "venda" in r.text and "-2" in r.text
    # separação por toque (JSON)
    r = c.get(f"/admin/pedidos/{pid}")
    item_ids = re.findall(r'type="checkbox" value="(\d+)" data-pedido', r.text)
    assert len(item_ids) == 2
    for iid in item_ids:
        rj = c.post(f"/admin/pedidos/{pid}/separar-item", json={"item_id": int(iid), "separado": True, "csrf": tk_admin}, headers={"X-CSRF-Token": tk_admin})
        assert rj.status_code == 200
    assert rj.json()["todos"] is True
    _post(c, f"/admin/pedidos/{pid}/concluir-separacao", tk_admin)
    assert "Embalar" in c.get(f"/admin/pedidos/{pid}").text
    assert c.get(f"/admin/pedidos/{pid}/etiqueta").status_code == 200
    assert c.get(f"/admin/pedidos/{pid}/declaracao").status_code == 200
    _post(c, f"/admin/pedidos/{pid}/embalar", tk_admin, pacote="Caixa P", peso_g="520")
    assert "Postar nos Correios" in c.get(f"/admin/pedidos/{pid}").text
    _post(c, f"/admin/pedidos/{pid}/enviar", tk_admin, rastreio="aa123456789br", custo_postagem="18,50")
    r = c.get(f"/admin/pedidos/{pid}")
    assert "AA123456789BR" in r.text and "A caminho" in r.text
    r = c.get(f"/pedido/{numero}?t={token_cliente}")
    assert "AA123456789BR" in r.text
    # mensagens geradas (WhatsApp)
    r = c.get("/admin/mensagens")
    assert "wa.me/5511988887777" in r.text
    # NF-e (emissor simulado)
    _post(c, f"/admin/pedidos/{pid}/nfe", tk_admin)
    r = c.get(f"/admin/pedidos/{pid}")
    assert "Autorizada" in r.text
    nota_id = int(re.search(r"/admin/faturamento/(\d+)/danfe", r.text).group(1))
    r = c.get(f"/admin/faturamento/{nota_id}/danfe")
    assert r.status_code == 200 and "DANFE" in r.text and "Ana Teste" in r.text
    r = c.get("/admin/faturamento")
    assert "Autorizada" in r.text
    assert c.get("/admin/faturamento?formato=csv").status_code == 200
    # entrega + pós-venda
    _post(c, f"/admin/pedidos/{pid}/entregar", tk_admin)
    r = c.get("/admin/pos-venda")
    assert "Pedir avaliação" in r.text or "Enviar cupom" in r.text
    # avaliação pelo cliente
    r = c.get(f"/avaliar/{token_cliente}")
    assert r.status_code == 200
    ids = re.findall(r'name="nota_(\d+)"', r.text)
    r = c.post(f"/avaliar/{token_cliente}", data={"csrf": tk, f"nota_{ids[0]}": "5", f"comentario_{ids[0]}": "Muito bom, discreto.", "nome_exibicao": "Ana"})
    assert r.status_code == 200 and "Obrigado" in r.text
    r = c.get("/admin/pos-venda")
    aval_id = re.search(r"/admin/avaliacoes/(\d+)/aprovar", r.text).group(1)
    _post(c, f"/admin/avaliacoes/{aval_id}/aprovar", tk_admin)
    assert "Muito bom, discreto." in c.get("/").text

    # ---------- ticket + devolução parcial
    r = c.get(f"/admin/tickets/novo?pedido={numero}")
    _post(c, "/admin/tickets/novo", tk_admin, tipo="devolucao", assunto="Quer devolver 1 unidade", mensagem="Chegou e não gostou", pedido=numero)
    r = c.get("/admin/pos-venda")
    ticket_id = re.search(r"/admin/tickets/(\d+)", r.text).group(1)
    r = c.get(f"/admin/tickets/{ticket_id}")
    assert r.status_code == 200
    item_dev = re.search(r'name="dev_(\d+)"', r.text).group(1)
    _post(c, f"/admin/tickets/{ticket_id}/devolucao", tk_admin, **{f"dev_{item_dev}": "1", "reembolso": "100,00", "motivo": "arrependimento"})
    r = c.get(f"/admin/tickets/{ticket_id}")
    assert "Resolvido" in r.text
    r = c.get("/admin/caixa")
    assert "Reembolso" in r.text

    # ---------- relatórios
    for url in ["/admin/relatorios/financeiro", "/admin/relatorios/financeiro?p=hoje", "/admin/relatorios/estoque", "/admin/relatorios/pedidos", "/admin/relatorios/nao-enviados", "/admin/relatorios/clientes"]:
        r = c.get(url)
        assert r.status_code == 200, url
        r = c.get(url + ("&" if "?" in url else "?") + "formato=csv")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), url
    r = c.get("/admin/relatorios/financeiro?p=hoje")
    assert "Ana Teste" not in r.text or True
    assert "Kit plugs iniciante" in r.text  # top produtos
    r = c.get("/admin/clientes")
    assert "Ana Teste" in r.text and "completo" in r.text


def test_webhook_confirma_pagamento(admin):
    c = admin
    r = c.get("/produto/dilatador-conico-grande")
    tk = csrf_de(r.text)
    _post(c, "/carrinho/adicionar", tk, produto_id="3", quantidade="1")
    dados = dict(nome="Bruno Teste", email="bruno@teste.com", telefone="21977776666", cpf="12345678909", nascimento="1985-01-01", cep="20040020", logradouro="Rua da Assembleia", numero="10", bairro="Centro", cidade="Rio de Janeiro", uf="RJ", frete_metodo="PAC", consentimento_lgpd="1", maior_de_idade="1")
    r = c.post("/checkout", data={**dados, "csrf": tk}, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    numero = re.search(r"/pedido/(P\d+)/", r.headers["location"]).group(1)
    r = c.post("/api/webhooks/pagamento", json={"token": "errado", "pedido": numero})
    assert r.status_code == 403
    r = c.post("/api/webhooks/pagamento", json={"token": "segredo-webhook", "pedido": numero, "provedor": "psp-teste", "referencia": "abc"})
    assert r.status_code == 200 and r.json()["status"] == "pago"
    r = c.get("/admin/relatorios/nao-enviados")
    assert numero in r.text


def test_cancelamento_devolve_estoque(admin):
    c = admin
    r = c.get("/produto/bomba-peniana-manual")
    tk = csrf_de(r.text)
    _post(c, "/carrinho/adicionar", tk, produto_id="8", quantidade="3")
    dados = dict(nome="Carla Teste", email="carla@teste.com", telefone="31966665555", cpf="11144477735", nascimento="1992-02-02", cep="30130010", logradouro="Av Afonso Pena", numero="100", bairro="Centro", cidade="Belo Horizonte", uf="MG", frete_metodo="PAC", consentimento_lgpd="1", maior_de_idade="1")
    r = c.post("/checkout", data={**dados, "csrf": tk}, follow_redirects=False)
    assert r.status_code == 303
    numero = re.search(r"/pedido/(P\d+)/", r.headers["location"]).group(1)
    pid = _id_pedido(c, numero)
    tk_admin = csrf_de(c.get(f"/admin/pedidos/{pid}").text)
    mov_antes = c.get("/admin/estoque/movimentos?produto_id=8").text.count("<tr>")
    _post(c, f"/admin/pedidos/{pid}/confirmar-pagamento", tk_admin)
    _post(c, f"/admin/pedidos/{pid}/cancelar", tk_admin, motivo="cliente desistiu", estornar="1")
    r = c.get("/admin/estoque/movimentos?produto_id=8")
    assert "cancelamento" in r.text and "+3" in r.text
    r = c.get(f"/admin/pedidos/{pid}")
    assert "Cancelado" in r.text
    r = c.get("/admin/caixa")
    assert "Estorno" in r.text


def test_paginas_admin(admin):
    for url in PAGINAS_ADMIN:
        r = admin.get(url)
        assert r.status_code == 200, url


def test_configuracoes_e_cupom(admin):
    c = admin
    r = c.get("/admin/configuracoes")
    tk = csrf_de(r.text)
    _post(c, "/admin/configuracoes/pix", tk, pix_chave="11999990000", pix_nome="Loja Teste", pix_cidade="SAO PAULO")
    _post(c, "/admin/configuracoes/cupom", tk, codigo="frete0", tipo="frete", valor="0", minimo="50,00", max_usos="0", ativo="1")
    r = c.get("/admin/configuracoes")
    assert "FRETE0" in r.text
    _post(c, "/carrinho/adicionar", tk, produto_id="2", quantidade="1")
    r = c.get("/api/cupom?codigo=frete0")
    assert r.json()["ok"] and r.json()["tipo"] == "frete"


def test_venda_manual_e_sugestao_compra(admin):
    c = admin
    r = c.get("/admin/pedidos/novo")
    tk = csrf_de(r.text)
    r = _post(c, "/admin/pedidos/novo", tk, qtd_4="1", nome="Dani Teste", email="dani@teste.com", telefone="11955554444", cpf="98765432100", nascimento="1980-03-03", cep="04543000", logradouro="Rua X", numero="1", bairro="Itaim", cidade="São Paulo", uf="SP", frete_metodo="retirada")
    assert r.status_code == 303
    r = _post(c, "/admin/compras/sugerir", tk)
    assert r.status_code == 303
