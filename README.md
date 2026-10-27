# OnlineStore — loja virtual para uma pessoa só

Sex shop online para homens gays e bissexuais, pensada para ser operada por **uma pessoa**: o site vende,
o painel diz o que fazer hoje, e as regras chatas (baixar estoque, lançar no caixa, agendar o
pós-venda, cancelar PIX vencido, sugerir compra, emitir nota) acontecem sozinhas.

> Sexo salva vidas. Sexo é safado — e não é sujo, nem demoníaco. É um ato natural da vida.

## O que tem

| Área | O que faz |
|---|---|
| **Site (vitrine)** | Catálogo por categoria, busca, página de produto com avaliações, carrinho, checkout com KYC (CPF válido, 18+, consentimento LGPD), frete por CEP, cupom, **PIX com QR code e copia-e-cola**, acompanhamento do pedido por link, avaliação pós-compra, contato, páginas legais. Porta de entrada 18+. Funciona no celular. |
| **Hoje (painel)** | A fila do dia na ordem certa: PIX a confirmar → separar → embalar → postar → entregas atrasadas → pós-venda → tickets → repor estoque → NF-e pendentes → compras a pagar. KPIs de vendas, margem, caixa e estoque. |
| **Pedidos** | Confirmação de PIX (manual ou webhook), **separação por toque** com localização na prateleira, embalagem, envio com rastreio e custo de postagem, entrega, cancelamento com estorno, venda manual (WhatsApp/Instagram), etiqueta 10×15 e declaração de conteúdo para os Correios. |
| **Estoque** | Movimentos auditáveis (compra, venda, ajuste, devolução, cancelamento), custo médio ponderado, giro de 30 dias, cobertura em dias, **sugestão de compra** por fornecedor com um clique. |
| **Compras (cash-out)** | Pedido ao fornecedor → recebimento (entra estoque, recalcula custo) → pagamento (sai do caixa). Fornecedores com prazo de entrega. |
| **Caixa (cash-in/out)** | Livro-caixa automático: venda, estorno, compra, postagem; despesas manuais. Saldo, extrato por período. |
| **Pós-venda** | Follow-ups automáticos (confirmar entrega, pedir avaliação, cupom de retorno) com mensagem de WhatsApp pronta; tickets de dúvida/troca/devolução; devolução dá entrada no estoque e saída no caixa; moderação de avaliações. |
| **Clientes (KYC)** | Ficha com validações (CPF, idade, contato, endereço, consentimento), histórico, LTV, recorrência, inativos, aceite de marketing. |
| **Faturamento / NF-e** | NF-e modelo 55 por pedido via **Focus NFe** (ou emissor simulado para testar), emissão manual ou automática ao confirmar o PIX, cancelamento, DANFE, faturamento por mês e CSV para o contador. |
| **Relatórios** | Financeiro (receita, CMV, margem, frete, estornos, caixa, vendas por dia, top produtos), estoque, pedidos, **pagos e não enviados**, clientes — todos com CSV. |
| **Mensagens** | Cada etapa gera uma mensagem de WhatsApp (link pronto) e um e-mail (SMTP opcional). |

## Rodar em 2 minutos

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Abra http://localhost:8000/admin — o **primeiro acesso** cria sua senha e a chave PIX.
A loja já nasce com um catálogo de exemplo (22 produtos fictícios, imagens abstratas) para você
testar o fluxo inteiro; troque pelos seus produtos em *Painel → Produtos*.

Testes: `pytest` (fluxo ponta a ponta: compra → venda → PIX → separação → envio → NF-e → devolução → relatórios).

## Fluxo de um pedido

```
Site: carrinho → checkout (KYC) → PIX gerado ─┐
                                              ▼
Hoje: [PIX recebido] → estoque baixa, caixa entra, NF-e (se automática)
      → [Separar] toque em cada item (localização) → [Embalar] etiqueta + DANFE/declaração
      → [Enviado] código de rastreio + custo da postagem → cliente recebe WhatsApp/e-mail
      → [Entregue] → pós-venda: D+3 pedir avaliação, D+30 cupom de retorno
```

Pedidos sem PIX por 24 h são cancelados sozinhos (3× isso se o cliente clicou em "Já paguei").

## Configurar para valer

Tudo em **Painel → Configurações**:

1. **Loja** — nome, frase, manifesto, WhatsApp, Instagram.
2. **PIX** — chave e nome do recebedor (aparece no app do banco). O QR é estático com valor e
   identificador do pedido; a confirmação é o botão "PIX recebido".
3. **Remetente** — nome neutro e endereço para a etiqueta (embalagem discreta).
4. **Frete** — tabela por região (PAC/SEDEX, até 1 kg) e frete grátis acima de X. Calibre com o
   balcão dos Correios.
5. **Cupons**, **Automações** (prazos do pós-venda, cancelamento automático, NF-e automática).
6. **Fiscal** — CNPJ, IE, endereço, regime, numeração e códigos (CFOP/CSOSN/PIS/COFINS).

### NF-e de verdade (Focus NFe)

1. Crie conta em https://focusnfe.com.br, cadastre a empresa e o **certificado A1**.
2. No `.env`: `FOCUS_NFE_TOKEN=...` e `FOCUS_NFE_AMBIENTE=homologacao` (depois `producao`).
3. Preencha *Configurações → Fiscal* e o **NCM** de cada produto (confirme com o contador —
   os códigos do catálogo de exemplo são sugestões).
4. Emita em *Pedidos → NF-e* ou ligue "emitir automaticamente" em Automações.

Sem token, a loja usa um **emissor simulado**: autoriza na hora, gera chave válida e DANFE
de teste, para você treinar o fluxo sem valor fiscal.

### Confirmação automática de PIX (depois)

Hoje a conferência é manual (uma pessoa, poucos pedidos por dia, extrato do banco). Quando
quiser automatizar, ligue um PSP (Mercado Pago, Asaas, Pagar.me, Efí) e aponte o webhook para:

```
POST /api/webhooks/pagamento
{"token": "<WEBHOOK_TOKEN do .env>", "pedido": "P1001", "provedor": "asaas", "referencia": "id-da-cobranca"}
```

O pedido vira "pago", o estoque baixa, o caixa entra e a NF-e sai, igual ao botão.

## Publicar na internet

**Docker** (Railway, Render, Fly.io, VPS):

```bash
docker compose up -d        # dados persistem no volume "dados"
```

Defina `BASE_URL=https://seudominio.com.br` no `.env` (os links enviados ao cliente usam isso)
e coloque um proxy com HTTPS na frente (Caddy, Nginx, ou o da própria plataforma).

**Backup**: copie a pasta `data/` (banco SQLite + imagens). É tudo.

Esqueceu a senha? `python scripts/resetar_senha.py seu@email.com NovaSenha123`.
Quer o catálogo de exemplo mais novo do código (antes de ter pedidos)? `python scripts/recarregar_catalogo.py`.

## Estrutura

```
app/
  main.py            # app FastAPI, automações em background
  models.py          # tabelas (pedidos, itens, estoque, compras, caixa, clientes, tickets, notas…)
  services/          # regras de negócio
    pedidos.py       # carrinho → pedido → pago → separado → embalado → enviado → entregue
    estoque.py       # movimentos, cobertura, sugestão de compra
    compras.py       # pedido ao fornecedor, recebimento, pagamento
    caixa.py         # livro-caixa
    pagamentos.py    # PIX BR Code + QR
    frete.py         # tabela por região, rastreio
    clientes.py      # KYC e insights
    posvenda.py      # follow-ups, tickets, devoluções, avaliações
    faturamento.py   # NF-e (Focus NFe / simulado), DANFE, faturamento por mês
    notificacoes.py  # textos de WhatsApp/e-mail por etapa
    automacoes.py    # fila do dia, KPIs, regras automáticas
    relatorios.py    # relatórios e CSV
    assistente.py    # opcional: API da Claude
  web/loja.py        # vitrine        web/api.py  # frete, cupom, webhook
  web/admin/         # painel (uma rota por módulo)
  templates/         # loja/, admin/, impressao/ (etiqueta, declaração, DANFE)
  static/            # css, js, imagens de exemplo
tests/               # fluxo ponta a ponta
scripts/             # resetar senha, gerar imagens de exemplo
```

Stack: Python 3.10+, FastAPI, SQLAlchemy + SQLite, Jinja2, CSS e JS sem build. Tema escuro (site e painel); as cores são variáveis no topo de `app/static/css/loja.css` e `admin.css`. Um processo, um
arquivo de banco, roda em qualquer máquina.

## Decisões e placeholders (para ajustar depois)

- **Nome da loja** "Pêssego" e slogan são placeholders — troque em Configurações → Loja.
- **Preços de frete** são aproximações de balcão; sem contrato dos Correios não há API de preço.
- **Códigos fiscais** padrão (CFOP 5102/6102, CSOSN 102, PIS/COFINS 49, NCMs do catálogo) são os
  mais comuns para Simples Nacional; o contador confirma.
- **Reconciliação bancária** fica para depois: hoje a confirmação de PIX é manual ou por webhook.
- **Imagens** dos produtos de exemplo são abstratas, de propósito; suba as fotos reais no painel.
