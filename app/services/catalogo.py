"""Catálogo: categorias, produtos, imagens e a carga inicial de exemplo."""
from __future__ import annotations

import re
import secrets
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import config
from ..models import Avaliacao, Categoria, Cupom, Fornecedor, Produto
from ..utils import slugify
from . import frete

EXTENSOES_IMAGEM = {"jpg", "jpeg", "png", "webp", "gif"}  # sem SVG: upload de SVG pode carregar script


def categorias(db: Session, somente_ativas: bool = True) -> list[Categoria]:
    q = select(Categoria).order_by(Categoria.ordem, Categoria.nome)
    if somente_ativas:
        q = q.where(Categoria.ativa.is_(True))
    return list(db.execute(q).scalars())


def produtos(db: Session, categoria_slug: str | None = None, busca: str = "", ordem: str = "destaque", somente_ativos: bool = True, limite: int = 500) -> list[Produto]:
    q = select(Produto).limit(limite)
    if somente_ativos:
        q = q.where(Produto.ativo.is_(True))
    if categoria_slug:
        q = q.join(Categoria, Categoria.id == Produto.categoria_id).where(Categoria.slug == categoria_slug)
    if busca:
        termo = f"%{busca.strip()}%"
        q = q.where(Produto.nome.ilike(termo) | Produto.descricao.ilike(termo) | Produto.sku.ilike(termo))
    if ordem == "menor_preco":
        q = q.order_by(Produto.preco_cents)
    elif ordem == "maior_preco":
        q = q.order_by(Produto.preco_cents.desc())
    elif ordem == "nome":
        q = q.order_by(Produto.nome)
    elif ordem == "novos":
        q = q.order_by(Produto.id.desc())
    else:
        q = q.order_by(Produto.destaque.desc(), (Produto.estoque > 0).desc(), Produto.nome)
    return list(db.execute(q).scalars())


def por_slug(db: Session, slug: str) -> Produto | None:
    return db.execute(select(Produto).where(Produto.slug == slug)).scalar_one_or_none()


def destaques(db: Session, limite: int = 8) -> list[Produto]:
    return list(db.execute(select(Produto).where(Produto.ativo.is_(True), Produto.destaque.is_(True), Produto.estoque > 0).order_by(Produto.id.desc()).limit(limite)).scalars())


def relacionados(db: Session, produto: Produto, limite: int = 4) -> list[Produto]:
    q = select(Produto).where(Produto.ativo.is_(True), Produto.id != produto.id, Produto.estoque > 0)
    if produto.categoria_id:
        q = q.where(Produto.categoria_id == produto.categoria_id)
    return list(db.execute(q.order_by(Produto.destaque.desc()).limit(limite)).scalars())


def media_avaliacoes(db: Session, produto_id: int) -> tuple[float, int]:
    media, n = db.execute(select(func.avg(Avaliacao.nota), func.count(Avaliacao.id)).where(Avaliacao.produto_id == produto_id, Avaliacao.aprovada.is_(True))).one()
    return (round(float(media), 1) if media else 0.0, int(n or 0))


def slug_unico(db: Session, nome: str, produto_id: int | None = None) -> str:
    base = slugify(nome)
    slug = base
    n = 2
    while True:
        existente = db.execute(select(Produto).where(Produto.slug == slug)).scalar_one_or_none()
        if not existente or existente.id == produto_id:
            return slug
        slug = f"{base}-{n}"
        n += 1


def sku_unico(db: Session, sku: str, produto_id: int | None = None) -> str:
    sku = re.sub(r"[^A-Z0-9\-]", "", (sku or "").upper()) or f"SKU{secrets.randbelow(9000) + 1000}"
    base = sku
    n = 2
    while True:
        existente = db.execute(select(Produto).where(Produto.sku == sku)).scalar_one_or_none()
        if not existente or existente.id == produto_id:
            return sku
        sku = f"{base}-{n}"
        n += 1


def salvar_imagem(nome_arquivo: str, conteudo: bytes) -> str:
    """Grava em data/uploads e devolve o nome relativo (servido em /media/...)."""
    ext = (nome_arquivo.rsplit(".", 1)[-1] if "." in nome_arquivo else "").lower()
    if ext not in EXTENSOES_IMAGEM:
        raise ValueError("Use uma imagem JPG, PNG, WEBP ou GIF.")
    if len(conteudo) > 6 * 1024 * 1024:
        raise ValueError("Imagem muito grande (máximo 6 MB).")
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{secrets.token_hex(8)}.{ext}"
    Path(config.UPLOAD_DIR / nome).write_bytes(conteudo)
    return nome


# ------------------------------------------------------------------- seed
CATEGORIAS_INICIAIS = [
    ("Vibradores e massageadores", "vibradores", "Para explorar sozinho ou em dupla."),
    ("Lubrificantes e géis", "lubrificantes", "Conforto é parte do prazer."),
    ("Preservativos", "preservativos", "Sexo seguro é sexo melhor."),
    ("Bem-estar íntimo", "bem-estar", "Saúde pélvica, cuidado e autoconhecimento."),
    ("Cosméticos sensuais", "cosmeticos", "Óleos, velas e sabores para o clima."),
    ("Acessórios e jogos", "acessorios", "Brincadeiras para dois."),
    ("Lingerie", "lingerie", "Para se sentir bem na própria pele."),
]

FORNECEDORES_INICIAIS = [
    ("Distribuidora Íntima SP", "Carla", "11988880001", "vendas@intimasp.exemplo", 5),
    ("Importadora Prazer & Cia", "Marcos", "11977770002", "pedidos@prazerecia.exemplo", 12),
]

# sku, nome, categoria_slug, fornecedor_idx, preco, custo, estoque, min, peso_g, ncm, destaque, resumo, descricao
PRODUTOS_INICIAIS = [
    ("VIB-001", "Vibrador ponto G Onda", "vibradores", 1, 18990, 7900, 14, 3, 220, "9019.10.00", True,
     "Silicone macio, 10 modos, recarregável por USB.",
     "Curva pensada para o ponto G, silicone de toque aveludado e motor silencioso. Dez modos de vibração, "
     "à prova d'água, recarregável por USB (cabo incluso). Autonomia de cerca de 90 minutos."),
    ("VIB-002", "Sugador clitoriano Brisa", "vibradores", 1, 24990, 10500, 9, 3, 180, "9019.10.00", True,
     "Estímulo por ondas de ar, 7 intensidades.",
     "Tecnologia de ondas de ar sem contato direto, sete intensidades e formato que cabe na mão. "
     "Silicone hipoalergênico, à prova d'água, carregamento magnético."),
    ("VIB-003", "Bullet vibratório Pílula", "vibradores", 1, 6990, 2400, 25, 5, 60, "9019.10.00", False,
     "Pequeno, discreto e potente. Ideal para começar.",
     "Vibrador bullet de 7 cm com três velocidades. Cabe em qualquer bolsa, funciona com uma pilha AAA (inclusa)."),
    ("VIB-004", "Massageador de próstata Pulso", "vibradores", 2, 21990, 9800, 6, 2, 210, "9019.10.00", False,
     "Formato anatômico, controle remoto e 9 modos.",
     "Pensado para o estímulo prostático e perineal ao mesmo tempo. Base de segurança larga, controle remoto, "
     "silicone de grau médico. Recarregável."),
    ("LUB-001", "Lubrificante à base de água 100 ml", "lubrificantes", 1, 3490, 1300, 60, 10, 130, "3006.70.00", True,
     "Neutro, sem cheiro, compatível com silicone e látex.",
     "Fórmula à base de água, pH equilibrado, sem parabenos nem glicerina. Compatível com preservativos e "
     "brinquedos de silicone. Frasco com bico dosador."),
    ("LUB-002", "Lubrificante siliconado 50 ml", "lubrificantes", 2, 5990, 2600, 30, 6, 80, "3006.70.00", False,
     "Dura mais, ótimo para anal. Não usar com brinquedos de silicone.",
     "Toque sedoso e de longa duração. Não resseca, não precisa reaplicar. Indicado para sexo anal e para o chuveiro. "
     "Evite usar com brinquedos de silicone."),
    ("LUB-003", "Gel beijável morango 40 ml", "lubrificantes", 1, 2990, 1100, 40, 8, 70, "3006.70.00", False,
     "Sabor leve para o sexo oral.",
     "Gel comestível com sabor suave de morango, à base de água. Sem açúcar."),
    ("PRE-001", "Preservativo ultrafino (cx. 12)", "preservativos", 1, 3290, 1400, 80, 15, 60, "4014.10.00", False,
     "Látex natural, lubrificado, mais sensibilidade.",
     "Doze preservativos de látex ultrafinos, lubrificados, testados eletronicamente. Registro na Anvisa."),
    ("PRE-002", "Preservativo texturizado (cx. 12)", "preservativos", 1, 3490, 1500, 50, 10, 60, "4014.10.00", False,
     "Com pontos e frisos, lubrificado.",
     "Doze preservativos texturizados para mais estímulo, lubrificados, látex natural."),
    ("BEM-001", "Kit pompoarismo 3 bolinhas", "bem-estar", 2, 8990, 3600, 18, 4, 150, "9019.10.00", True,
     "Pesos progressivos para fortalecer o assoalho pélvico.",
     "Três bolinhas de silicone com pesos progressivos (30 g, 45 g e 60 g) para exercícios de pompoarismo. "
     "Fortalece o assoalho pélvico, melhora o controle e a sensibilidade. Guia de exercícios incluso."),
    ("BEM-002", "Dilatador anal progressivo (3 tamanhos)", "bem-estar", 2, 9990, 4100, 12, 3, 240, "9019.10.00", False,
     "Para começar com calma, no seu ritmo.",
     "Três plugs de silicone em tamanhos progressivos, base larga de segurança. Para quem quer explorar o sexo anal "
     "com conforto. Use sempre com lubrificante."),
    ("COS-001", "Óleo de massagem morno baunilha 120 ml", "cosmeticos", 1, 4990, 1900, 35, 6, 160, "3304.99.90", False,
     "Esquenta no contato com a pele.",
     "Óleo de massagem com efeito morno, aroma de baunilha e textura que desliza sem deixar a pele pegajosa."),
    ("COS-002", "Vela de massagem lavanda", "cosmeticos", 2, 5990, 2300, 20, 4, 210, "3406.00.00", True,
     "A cera vira óleo de massagem morno.",
     "Vela de soja que derrete em óleo morno para massagem. Aroma de lavanda, pavio de algodão, 60 h de queima."),
    ("ACE-001", "Venda de cetim + algemas de pelúcia", "acessorios", 2, 6990, 2500, 22, 4, 120, "6307.90.90", False,
     "Kit iniciante para brincar de confiança.",
     "Venda de cetim macia e algemas de pelúcia com fecho de velcro — soltam com um puxão. Para começar devagar."),
    ("ACE-002", "Jogo de cartas Dupla", "acessorios", 1, 4490, 1500, 30, 5, 110, "9504.90.90", False,
     "100 cartas com desafios para casais.",
     "Baralho com desafios em três níveis — do romântico ao ousado. Para abrir conversa e descobrir vontades."),
    ("ACE-003", "Anel peniano vibratório", "acessorios", 2, 4990, 1800, 28, 5, 50, "3926.90.90", False,
     "Prolonga a ereção e vibra para os dois.",
     "Anel de silicone elástico com vibrador acoplado. Pilha inclusa. Estimula quem usa e quem está junto."),
    ("LIN-001", "Conjunto de renda Noite — P/M/G", "lingerie", 1, 12990, 5200, 10, 2, 140, "6108.22.00", True,
     "Renda macia, alças ajustáveis. Informe o tamanho no pedido.",
     "Conjunto de sutiã e calcinha em renda macia com alças ajustáveis. Tamanhos P, M e G — escreva o tamanho na "
     "observação do pedido."),
]


def seed_se_vazio(db: Session) -> bool:
    """Carga de exemplo (produtos fictícios) para a loja não nascer vazia."""
    if db.execute(select(Produto.id).limit(1)).first():
        frete.garantir_tabela(db)
        return False
    cats: dict[str, Categoria] = {}
    for ordem, (nome, slug, desc) in enumerate(CATEGORIAS_INICIAIS):
        c = Categoria(nome=nome, slug=slug, descricao=desc, ordem=ordem)
        db.add(c)
        cats[slug] = c
    forns: list[Fornecedor] = []
    for nome, contato, tel, email, prazo in FORNECEDORES_INICIAIS:
        f = Fornecedor(nome=nome, contato=contato, telefone=tel, email=email, prazo_dias=prazo)
        db.add(f)
        forns.append(f)
    db.flush()
    for sku, nome, cat, forn_idx, preco, custo, est, minimo, peso, ncm, destaque, resumo, descricao in PRODUTOS_INICIAIS:
        db.add(
            Produto(
                sku=sku, nome=nome, slug=slugify(nome), categoria_id=cats[cat].id, fornecedor_id=forns[forn_idx - 1].id,
                preco_cents=preco, custo_cents=custo, estoque=est, estoque_minimo=minimo, peso_g=peso, ncm=ncm,
                destaque=destaque, resumo=resumo, descricao=descricao, imagem=f"/static/img/produtos/{sku}.svg",
                localizacao=f"{cat[:3].upper()}-{sku[-3:]}",
            )
        )
    db.add(Cupom(codigo="VOLTA10", tipo="percentual", valor=10, minimo_cents=5000))
    db.add(Cupom(codigo="BEMVINDO", tipo="fixo", valor=1500, minimo_cents=9900))
    frete.garantir_tabela(db)
    db.flush()
    return True
