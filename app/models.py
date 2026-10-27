"""Modelo de dados da loja.

Dinheiro é sempre guardado em centavos (int). Datas no horário local da loja.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .utils import agora


# ------------------------------------------------------------------ status
class StatusPedido:
    AGUARDANDO = "aguardando_pagamento"
    PAGO = "pago"
    SEPARADO = "separado"
    EMBALADO = "embalado"
    ENVIADO = "enviado"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"
    DEVOLVIDO = "devolvido"

    ORDEM = [AGUARDANDO, PAGO, SEPARADO, EMBALADO, ENVIADO, ENTREGUE]
    ABERTOS = [AGUARDANDO, PAGO, SEPARADO, EMBALADO, ENVIADO]
    PAGOS = [PAGO, SEPARADO, EMBALADO, ENVIADO, ENTREGUE, DEVOLVIDO]
    PAGOS_NAO_ENVIADOS = [PAGO, SEPARADO, EMBALADO]

    LABELS = {
        AGUARDANDO: "Aguardando PIX",
        PAGO: "Pago · a separar",
        SEPARADO: "Separado · a embalar",
        EMBALADO: "Embalado · a postar",
        ENVIADO: "Enviado",
        ENTREGUE: "Entregue",
        CANCELADO: "Cancelado",
        DEVOLVIDO: "Devolvido",
    }
    LABELS_CLIENTE = {
        AGUARDANDO: "Aguardando pagamento",
        PAGO: "Pagamento confirmado",
        SEPARADO: "Em separação",
        EMBALADO: "Embalado",
        ENVIADO: "A caminho",
        ENTREGUE: "Entregue",
        CANCELADO: "Cancelado",
        DEVOLVIDO: "Devolvido",
    }


class StatusCompra:
    RASCUNHO = "rascunho"
    ENVIADA = "enviada"
    RECEBIDA = "recebida"
    CANCELADA = "cancelada"
    LABELS = {RASCUNHO: "Rascunho", ENVIADA: "Enviada ao fornecedor", RECEBIDA: "Recebida", CANCELADA: "Cancelada"}


class StatusNota:
    PROCESSANDO = "processando"
    AUTORIZADA = "autorizada"
    CANCELADA = "cancelada"
    ERRO = "erro"
    LABELS = {PROCESSANDO: "Processando", AUTORIZADA: "Autorizada", CANCELADA: "Cancelada", ERRO: "Erro"}


class TipoMovimento:
    COMPRA = "compra"
    VENDA = "venda"
    AJUSTE = "ajuste"
    DEVOLUCAO = "devolucao"
    PERDA = "perda"
    CANCELAMENTO = "cancelamento"
    LABELS = {COMPRA: "Compra", VENDA: "Venda", AJUSTE: "Ajuste", DEVOLUCAO: "Devolução", PERDA: "Perda/avaria", CANCELAMENTO: "Cancelamento"}


class TipoFollowUp:
    CONFIRMAR_ENTREGA = "confirmar_entrega"
    PEDIR_AVALIACAO = "pedir_avaliacao"
    CUPOM_RETORNO = "cupom_retorno"
    REPOSICAO = "reposicao"
    LABELS = {
        CONFIRMAR_ENTREGA: "Confirmar se chegou",
        PEDIR_AVALIACAO: "Pedir avaliação",
        CUPOM_RETORNO: "Enviar cupom de retorno",
        REPOSICAO: "Lembrar reposição",
    }


class TipoTicket:
    DUVIDA = "duvida"
    TROCA = "troca"
    DEVOLUCAO = "devolucao"
    RECLAMACAO = "reclamacao"
    ELOGIO = "elogio"
    LABELS = {DUVIDA: "Dúvida", TROCA: "Troca", DEVOLUCAO: "Devolução", RECLAMACAO: "Reclamação", ELOGIO: "Elogio"}


# ------------------------------------------------------------------ tabelas
class Configuracao(Base):
    __tablename__ = "configuracoes"
    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, default="")


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(300))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    descricao: Mapped[str] = mapped_column(Text, default="")
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)

    produtos: Mapped[list["Produto"]] = relationship(back_populates="categoria")


class Fornecedor(Base):
    __tablename__ = "fornecedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    contato: Mapped[str] = mapped_column(String(120), default="")
    telefone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    prazo_dias: Mapped[int] = mapped_column(Integer, default=7)  # prazo médio de entrega do fornecedor
    observacoes: Mapped[str] = mapped_column(Text, default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    produtos: Mapped[list["Produto"]] = relationship(back_populates="fornecedor")
    compras: Mapped[list["Compra"]] = relationship(back_populates="fornecedor")


class Produto(Base):
    __tablename__ = "produtos"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"), nullable=True)
    descricao: Mapped[str] = mapped_column(Text, default="")
    resumo: Mapped[str] = mapped_column(String(200), default="")
    preco_cents: Mapped[int] = mapped_column(Integer, default=0)
    custo_cents: Mapped[int] = mapped_column(Integer, default=0)  # custo médio
    estoque: Mapped[int] = mapped_column(Integer, default=0)
    estoque_minimo: Mapped[int] = mapped_column(Integer, default=2)
    peso_g: Mapped[int] = mapped_column(Integer, default=200)
    localizacao: Mapped[str] = mapped_column(String(40), default="")  # prateleira/caixa onde está guardado
    imagem: Mapped[str] = mapped_column(String(300), default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    destaque: Mapped[bool] = mapped_column(Boolean, default=False)
    # Dados fiscais (NF-e). Confirme os códigos com o contador.
    ncm: Mapped[str] = mapped_column(String(10), default="")
    cest: Mapped[str] = mapped_column(String(10), default="")
    origem: Mapped[str] = mapped_column(String(1), default="0")  # 0 nacional, 1/2 importado...
    unidade: Mapped[str] = mapped_column(String(6), default="UN")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    categoria: Mapped["Categoria | None"] = relationship(back_populates="produtos")
    fornecedor: Mapped["Fornecedor | None"] = relationship(back_populates="produtos")
    movimentos: Mapped[list["MovimentoEstoque"]] = relationship(back_populates="produto", order_by="MovimentoEstoque.id.desc()")
    avaliacoes: Mapped[list["Avaliacao"]] = relationship(back_populates="produto")

    @property
    def imagem_url(self) -> str:
        if not self.imagem:
            return "/static/img/produtos/placeholder.svg"
        if self.imagem.startswith("/") or self.imagem.startswith("http"):
            return self.imagem
        return f"/media/{self.imagem}"

    @property
    def margem_pct(self) -> float:
        if not self.preco_cents:
            return 0.0
        return round(100.0 * (self.preco_cents - self.custo_cents) / self.preco_cents, 1)

    @property
    def estoque_baixo(self) -> bool:
        return self.ativo and self.estoque <= self.estoque_minimo


class MovimentoEstoque(Base):
    __tablename__ = "movimentos_estoque"
    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"))
    quantidade: Mapped[int] = mapped_column(Integer)  # positivo entra, negativo sai
    tipo: Mapped[str] = mapped_column(String(20))
    ref_tipo: Mapped[str] = mapped_column(String(20), default="")  # pedido, compra, ticket
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observacao: Mapped[str] = mapped_column(String(200), default="")
    saldo_apos: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    produto: Mapped["Produto"] = relationship(back_populates="movimentos")


class Compra(Base):
    """Pedido de compra ao fornecedor (entrada de estoque + saída de caixa)."""
    __tablename__ = "compras"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=StatusCompra.RASCUNHO)
    observacoes: Mapped[str] = mapped_column(Text, default="")
    frete_cents: Mapped[int] = mapped_column(Integer, default=0)
    pago: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    enviada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recebida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paga_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    previsao_entrega: Mapped[date | None] = mapped_column(Date, nullable=True)

    fornecedor: Mapped["Fornecedor | None"] = relationship(back_populates="compras")
    itens: Mapped[list["CompraItem"]] = relationship(back_populates="compra", cascade="all, delete-orphan")

    @property
    def total_itens_cents(self) -> int:
        return sum(i.quantidade * i.custo_unit_cents for i in self.itens)

    @property
    def total_cents(self) -> int:
        return self.total_itens_cents + (self.frete_cents or 0)


class CompraItem(Base):
    __tablename__ = "compra_itens"
    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"))
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"))
    quantidade: Mapped[int] = mapped_column(Integer, default=1)
    custo_unit_cents: Mapped[int] = mapped_column(Integer, default=0)
    recebido: Mapped[int] = mapped_column(Integer, default=0)

    compra: Mapped["Compra"] = relationship(back_populates="itens")
    produto: Mapped["Produto"] = relationship()


class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), index=True)
    telefone: Mapped[str] = mapped_column(String(30), default="")
    cpf: Mapped[str] = mapped_column(String(14), default="", index=True)
    nascimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    consentimento_lgpd: Mapped[bool] = mapped_column(Boolean, default=False)
    aceita_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    maior_de_idade_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    cep: Mapped[str] = mapped_column(String(9), default="")
    logradouro: Mapped[str] = mapped_column(String(200), default="")
    numero: Mapped[str] = mapped_column(String(20), default="")
    complemento: Mapped[str] = mapped_column(String(100), default="")
    bairro: Mapped[str] = mapped_column(String(100), default="")
    cidade: Mapped[str] = mapped_column(String(100), default="")
    uf: Mapped[str] = mapped_column(String(2), default="")
    observacoes: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    pedidos: Mapped[list["Pedido"]] = relationship(back_populates="cliente", order_by="Pedido.id.desc()")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="cliente")


class Pedido(Base):
    __tablename__ = "pedidos"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=StatusPedido.AGUARDANDO, index=True)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    frete_cents: Mapped[int] = mapped_column(Integer, default=0)
    desconto_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    cupom: Mapped[str] = mapped_column(String(30), default="")
    frete_metodo: Mapped[str] = mapped_column(String(30), default="")
    frete_prazo_dias: Mapped[int] = mapped_column(Integer, default=0)
    pagamento_metodo: Mapped[str] = mapped_column(String(20), default="pix")
    pix_txid: Mapped[str] = mapped_column(String(30), default="")
    pix_payload: Mapped[str] = mapped_column(Text, default="")
    cliente_informou_pagamento: Mapped[bool] = mapped_column(Boolean, default=False)
    token: Mapped[str] = mapped_column(String(60), default="", index=True)  # acesso do cliente à página do pedido
    # Snapshot do destinatário (o cliente pode mudar de endereço depois)
    nome: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    telefone: Mapped[str] = mapped_column(String(30), default="")
    cpf: Mapped[str] = mapped_column(String(14), default="")
    cep: Mapped[str] = mapped_column(String(9), default="")
    logradouro: Mapped[str] = mapped_column(String(200), default="")
    numero_end: Mapped[str] = mapped_column(String(20), default="")
    complemento: Mapped[str] = mapped_column(String(100), default="")
    bairro: Mapped[str] = mapped_column(String(100), default="")
    cidade: Mapped[str] = mapped_column(String(100), default="")
    uf: Mapped[str] = mapped_column(String(2), default="")
    # Expedição
    peso_g: Mapped[int] = mapped_column(Integer, default=0)
    pacote: Mapped[str] = mapped_column(String(40), default="")
    rastreio: Mapped[str] = mapped_column(String(40), default="")
    custo_postagem_cents: Mapped[int] = mapped_column(Integer, default=0)
    observacoes: Mapped[str] = mapped_column(Text, default="")
    observacoes_cliente: Mapped[str] = mapped_column(Text, default="")
    motivo_cancelamento: Mapped[str] = mapped_column(String(200), default="")
    origem: Mapped[str] = mapped_column(String(20), default="site")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)
    pago_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    separado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    embalado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped["Cliente | None"] = relationship(back_populates="pedidos")
    itens: Mapped[list["PedidoItem"]] = relationship(back_populates="pedido", cascade="all, delete-orphan")
    pagamentos: Mapped[list["Pagamento"]] = relationship(back_populates="pedido", cascade="all, delete-orphan")
    notas: Mapped[list["NotaFiscal"]] = relationship(back_populates="pedido", order_by="NotaFiscal.id.desc()")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="pedido")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="pedido")

    @property
    def label(self) -> str:
        return StatusPedido.LABELS.get(self.status, self.status)

    @property
    def label_cliente(self) -> str:
        return StatusPedido.LABELS_CLIENTE.get(self.status, self.status)

    @property
    def pago(self) -> bool:
        return self.status in StatusPedido.PAGOS

    @property
    def aberto(self) -> bool:
        return self.status in StatusPedido.ABERTOS

    @property
    def quantidade_itens(self) -> int:
        return sum(i.quantidade for i in self.itens)

    @property
    def custo_itens_cents(self) -> int:
        return sum(i.quantidade * i.custo_unit_cents for i in self.itens)

    @property
    def todos_separados(self) -> bool:
        return all(i.separado for i in self.itens)

    @property
    def nota_atual(self) -> "NotaFiscal | None":
        for n in self.notas:
            if n.status != StatusNota.CANCELADA:
                return n
        return self.notas[0] if self.notas else None

    @property
    def endereco_linha(self) -> str:
        partes = [f"{self.logradouro}, {self.numero_end}"]
        if self.complemento:
            partes.append(self.complemento)
        partes.append(f"{self.bairro} · {self.cidade}/{self.uf}")
        return " — ".join(partes)


class PedidoItem(Base):
    __tablename__ = "pedido_itens"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produtos.id"), nullable=True)
    sku: Mapped[str] = mapped_column(String(40), default="")
    nome: Mapped[str] = mapped_column(String(160))
    quantidade: Mapped[int] = mapped_column(Integer, default=1)
    preco_unit_cents: Mapped[int] = mapped_column(Integer, default=0)
    custo_unit_cents: Mapped[int] = mapped_column(Integer, default=0)
    separado: Mapped[bool] = mapped_column(Boolean, default=False)

    pedido: Mapped["Pedido"] = relationship(back_populates="itens")
    produto: Mapped["Produto | None"] = relationship()

    @property
    def total_cents(self) -> int:
        return self.quantidade * self.preco_unit_cents


class Pagamento(Base):
    __tablename__ = "pagamentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    metodo: Mapped[str] = mapped_column(String(20), default="pix")
    valor_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente, confirmado, estornado
    provedor: Mapped[str] = mapped_column(String(40), default="manual")
    referencia: Mapped[str] = mapped_column(String(100), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pedido: Mapped["Pedido"] = relationship(back_populates="pagamentos")


class LancamentoCaixa(Base):
    __tablename__ = "caixa"
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(10))  # entrada | saida
    categoria: Mapped[str] = mapped_column(String(30))  # venda, compra, frete, estorno, despesa, outro
    valor_cents: Mapped[int] = mapped_column(Integer)
    descricao: Mapped[str] = mapped_column(String(200), default="")
    ref_tipo: Mapped[str] = mapped_column(String(20), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    CATEGORIAS = {
        "venda": "Venda", "compra": "Compra de mercadoria", "frete": "Postagem/frete", "estorno": "Estorno",
        "embalagem": "Embalagem", "despesa": "Despesa", "imposto": "Imposto", "outro": "Outro",
    }


class Cupom(Base):
    __tablename__ = "cupons"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    tipo: Mapped[str] = mapped_column(String(12), default="percentual")  # percentual | fixo | frete
    valor: Mapped[int] = mapped_column(Integer, default=10)  # % ou centavos
    minimo_cents: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    usos: Mapped[int] = mapped_column(Integer, default=0)
    max_usos: Mapped[int] = mapped_column(Integer, default=0)  # 0 = ilimitado


class TabelaFrete(Base):
    __tablename__ = "tabela_frete"
    id: Mapped[int] = mapped_column(primary_key=True)
    metodo: Mapped[str] = mapped_column(String(20))  # PAC, SEDEX
    regiao: Mapped[str] = mapped_column(String(20))
    preco_cents: Mapped[int] = mapped_column(Integer)
    prazo_dias: Mapped[int] = mapped_column(Integer)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), default=TipoTicket.DUVIDA)
    status: Mapped[str] = mapped_column(String(20), default="aberto")  # aberto, em_andamento, resolvido
    assunto: Mapped[str] = mapped_column(String(200))
    nome: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    telefone: Mapped[str] = mapped_column(String(30), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped["Cliente | None"] = relationship(back_populates="tickets")
    pedido: Mapped["Pedido | None"] = relationship(back_populates="tickets")
    mensagens: Mapped[list["TicketMensagem"]] = relationship(back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMensagem.id")

    LABELS_STATUS = {"aberto": "Aberto", "em_andamento": "Em andamento", "resolvido": "Resolvido"}


class TicketMensagem(Base):
    __tablename__ = "ticket_mensagens"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    autor: Mapped[str] = mapped_column(String(10))  # cliente | loja
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    ticket: Mapped["Ticket"] = relationship(back_populates="mensagens")


class FollowUp(Base):
    """Tarefa de pós-venda gerada automaticamente (confirmar entrega, pedir avaliação...)."""
    __tablename__ = "followups"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos.id"), nullable=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(30))
    vence_em: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default="pendente")  # pendente, feito, pulado
    observacao: Mapped[str] = mapped_column(String(200), default="")
    feito_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    pedido: Mapped["Pedido | None"] = relationship(back_populates="followups")
    cliente: Mapped["Cliente | None"] = relationship()

    @property
    def label(self) -> str:
        return TipoFollowUp.LABELS.get(self.tipo, self.tipo)


class Avaliacao(Base):
    __tablename__ = "avaliacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"))
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos.id"), nullable=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    nota: Mapped[int] = mapped_column(Integer, default=5)
    comentario: Mapped[str] = mapped_column(Text, default="")
    nome_exibicao: Mapped[str] = mapped_column(String(60), default="")
    aprovada: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    produto: Mapped["Produto"] = relationship(back_populates="avaliacoes")


class Notificacao(Base):
    """Mensagens ao cliente. WhatsApp vira um link pronto; e-mail sai pelo SMTP (se configurado)."""
    __tablename__ = "notificacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos.id"), nullable=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    evento: Mapped[str] = mapped_column(String(40))
    canal: Mapped[str] = mapped_column(String(12))  # whatsapp | email
    destinatario: Mapped[str] = mapped_column(String(200), default="")
    assunto: Mapped[str] = mapped_column(String(200), default="")
    texto: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="pendente")  # pendente, enviada, falhou
    erro: Mapped[str] = mapped_column(String(300), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    enviada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pedido: Mapped["Pedido | None"] = relationship()


class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    numero: Mapped[int] = mapped_column(Integer)
    serie: Mapped[int] = mapped_column(Integer, default=1)
    chave: Mapped[str] = mapped_column(String(44), default="")
    status: Mapped[str] = mapped_column(String(20), default=StatusNota.PROCESSANDO)
    ambiente: Mapped[str] = mapped_column(String(20), default="simulado")  # simulado, homologacao, producao
    provedor: Mapped[str] = mapped_column(String(30), default="simulado")
    referencia: Mapped[str] = mapped_column(String(60), default="")  # ref no provedor
    protocolo: Mapped[str] = mapped_column(String(40), default="")
    xml_url: Mapped[str] = mapped_column(Text, default="")
    danfe_url: Mapped[str] = mapped_column(Text, default="")
    mensagem: Mapped[str] = mapped_column(Text, default="")
    valor_cents: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    justificativa: Mapped[str] = mapped_column(String(300), default="")
    emitida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    pedido: Mapped["Pedido"] = relationship(back_populates="notas")

    @property
    def label(self) -> str:
        return StatusNota.LABELS.get(self.status, self.status)


Index("ix_pedidos_status_criado", Pedido.status, Pedido.criado_em)
Index("ix_followups_status_vence", FollowUp.status, FollowUp.vence_em)
