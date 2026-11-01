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


def indice(db: Session) -> list[dict]:
    """Categorias com produto ativo, a contagem e uma imagem de capa (índice da home)."""
    por_categoria: dict[int, list[Produto]] = {}
    for p in produtos(db):
        por_categoria.setdefault(p.categoria_id, []).append(p)
    return [
        {"slug": c.slug, "nome": c.nome, "descricao": c.descricao, "n": len(lista), "capa": lista[0].imagem_url}
        for c in categorias(db)
        if (lista := por_categoria.get(c.id))
    ]


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
    ("Plugs e dilatadores", "plugs", "Do iniciante ao avançado, no seu ritmo."),
    ("Massageadores de próstata", "prostata", "O ponto P merece atenção."),
    ("Anéis e bombas", "aneis-bombas", "Mais firmeza, mais tempo."),
    ("Masturbadores", "masturbadores", "Para quando é só você."),
    ("Lubrificantes e géis", "lubrificantes", "Conforto é parte do prazer."),
    ("Preservativos", "preservativos", "Sexo seguro é sexo melhor."),
    ("Higiene e preparação", "higiene", "Para chegar tranquilo."),
    ("Cuecas e jockstraps", "cuecas-jocks", "Para se sentir bem na própria pele."),
    ("Fetiche e acessórios", "fetiche", "Brincadeiras de confiança."),
]

FORNECEDORES_INICIAIS = [
    ("Distribuidora Íntima SP", "Carla", "11988880001", "vendas@intimasp.exemplo", 5),
    ("Importadora Prazer & Cia", "Marcos", "11977770002", "pedidos@prazerecia.exemplo", 12),
]

# sku, nome, categoria_slug, fornecedor_idx, preco, custo, estoque, min, peso_g, ncm, destaque, resumo, descricao
PRODUTOS_INICIAIS = [
    ("PLG-001", "Kit plugs iniciante (3 tamanhos)", "plugs", 1, 9990, 4100, 14, 3, 240, "3926.90.90", True,
     "Três tamanhos progressivos, base larga, silicone macio.",
     "Três plugs de silicone em tamanhos progressivos, com base larga de segurança. Para começar com calma e ir "
     "avançando no seu ritmo. Use sempre com bastante lubrificante à base de água."),
    ("PLG-002", "Plug com vibração Pulso", "plugs", 1, 15990, 6800, 9, 3, 180, "9019.10.00", True,
     "10 modos, controle remoto, recarregável por USB.",
     "Plug de silicone com motor silencioso, dez modos de vibração e controle remoto — dá para entregar o controle "
     "para quem está com você. À prova d'água, recarregável por USB (cabo incluso)."),
    ("PLG-003", "Dilatador cônico Grande", "plugs", 2, 8990, 3600, 8, 2, 300, "3926.90.90", False,
     "Para quem já passou da fase iniciante.",
     "Dilatador cônico de silicone, firme e com base larga. Progressão natural para quem já usa o kit iniciante."),
    ("PRO-001", "Massageador de próstata Onda", "prostata", 1, 21990, 9800, 7, 2, 210, "9019.10.00", True,
     "Formato anatômico, 9 modos, controle remoto.",
     "Pensado para o estímulo prostático e perineal ao mesmo tempo. Curva anatômica, base de segurança, nove modos "
     "de vibração e controle remoto. Silicone de grau médico, recarregável."),
    ("PRO-002", "Massageador de próstata manual Curva", "prostata", 2, 11990, 4900, 10, 3, 160, "3926.90.90", False,
     "Sem motor: a curva faz o trabalho.",
     "Massageador manual com a curva certa para o ponto P. Silicone firme, sem pilha, fácil de higienizar."),
    ("ANE-001", "Kit 3 anéis penianos de silicone", "aneis-bombas", 1, 3990, 1400, 30, 6, 40, "3926.90.90", False,
     "Três diâmetros para achar o seu.",
     "Três anéis elásticos de silicone em diâmetros diferentes. Ajudam a manter a ereção mais firme por mais tempo."),
    ("ANE-002", "Anel peniano vibratório", "aneis-bombas", 2, 4990, 1800, 28, 5, 50, "3926.90.90", False,
     "Prolonga a ereção e vibra para os dois.",
     "Anel de silicone elástico com vibrador acoplado. Pilha inclusa. Estimula quem usa e quem está junto."),
    ("ANE-003", "Bomba peniana manual", "aneis-bombas", 2, 12990, 5200, 8, 2, 420, "9019.10.00", False,
     "Cilindro transparente com válvula de alívio.",
     "Bomba a vácuo manual com cilindro transparente, anel de vedação macio e válvula de alívio rápido. "
     "Para treino e para o momento."),
    ("MAS-001", "Masturbador egg (cx. 6)", "masturbadores", 1, 5990, 2300, 25, 5, 90, "3926.90.90", True,
     "Seis texturas diferentes, elástico e discreto.",
     "Caixa com seis masturbadores em formato de ovo, cada um com uma textura interna. Super elásticos, cabem "
     "na palma da mão. Lubrificante incluso em cada um."),
    ("MAS-002", "Masturbador de silicone Toque", "masturbadores", 2, 14990, 6100, 12, 3, 380, "3926.90.90", False,
     "Textura interna realista, fácil de lavar.",
     "Masturbador de silicone com canal texturizado e capa rígida. Abre para lavar. Use com lubrificante "
     "à base de água."),
    ("LUB-001", "Lubrificante à base de água 100 ml", "lubrificantes", 1, 3490, 1300, 60, 10, 130, "3006.70.00", True,
     "Neutro, sem cheiro, compatível com silicone e látex.",
     "Fórmula à base de água, pH equilibrado, sem parabenos nem glicerina. Compatível com preservativos e "
     "brinquedos de silicone. Frasco com bico dosador."),
    ("LUB-002", "Lubrificante siliconado 50 ml", "lubrificantes", 2, 5990, 2600, 30, 6, 80, "3006.70.00", False,
     "Dura mais, ótimo para anal. Não usar com brinquedos de silicone.",
     "Toque sedoso e de longa duração. Não resseca, não precisa reaplicar. Indicado para sexo anal e para o chuveiro. "
     "Evite usar com brinquedos de silicone."),
    ("LUB-003", "Gel anal de conforto 60 ml", "lubrificantes", 1, 4490, 1700, 35, 6, 90, "3006.70.00", False,
     "Mais espesso, sem anestésico.",
     "Gel à base de água mais espesso, feito para sexo anal. Sem anestésico de propósito: sentir é parte do cuidado. "
     "Compatível com preservativos e brinquedos."),
    ("PRE-001", "Preservativo ultrafino (cx. 12)", "preservativos", 1, 3290, 1400, 80, 15, 60, "4014.10.00", False,
     "Látex natural, lubrificado, mais sensibilidade.",
     "Doze preservativos de látex ultrafinos, lubrificados, testados eletronicamente. Registro na Anvisa."),
    ("PRE-002", "Preservativo tamanho grande (cx. 12)", "preservativos", 1, 3690, 1600, 50, 10, 60, "4014.10.00", False,
     "Mais largo, para não apertar nem estourar.",
     "Doze preservativos de látex com diâmetro maior, lubrificados. Camisinha apertada estoura; a certa protege."),
    ("HIG-001", "Ducha íntima anal (bulbo 220 ml)", "higiene", 2, 5990, 2200, 20, 4, 120, "3924.90.00", True,
     "Bico macio, fácil de limpar.",
     "Ducha de bulbo com bico de silicone macio e fluxo suave. Para se preparar com calma. Use só água morna; "
     "desmonta para secar."),
    ("HIG-002", "Toalhinhas íntimas (pct. 30)", "higiene", 1, 1990, 800, 40, 8, 110, "3401.19.00", False,
     "Para antes, durante e depois.",
     "Trinta toalhinhas umedecidas, pH neutro, sem perfume forte. Cabem na mochila."),
    ("ROU-001", "Jockstrap clássico — P/M/G", "cuecas-jocks", 1, 6990, 2900, 18, 4, 110, "6107.12.00", True,
     "Algodão com elástico largo. Informe o tamanho no pedido.",
     "Jockstrap de algodão com elástico largo e bolsa confortável. Tamanhos P, M e G — escreva o tamanho na "
     "observação do pedido."),
    ("ROU-002", "Cueca sungão em tule — P/M/G", "cuecas-jocks", 1, 5990, 2400, 15, 3, 80, "6107.12.00", False,
     "Transparente, elástico macio. Informe o tamanho.",
     "Cueca sungão em tule transparente com elástico macio. Tamanhos P, M e G — escreva o tamanho na observação."),
    ("FET-001", "Harness peitoral sintético", "fetiche", 2, 8990, 3500, 10, 2, 260, "6307.90.90", False,
     "Ajustável, fivelas metálicas.",
     "Harness peitoral em couro sintético com fivelas metálicas e tiras ajustáveis. Serve de P a GG."),
    ("FET-002", "Venda de cetim + algemas de pelúcia", "fetiche", 2, 6990, 2500, 22, 4, 120, "6307.90.90", False,
     "Kit iniciante para brincar de confiança.",
     "Venda de cetim macia e algemas de pelúcia com fecho de velcro — soltam com um puxão. Para começar devagar."),
    ("FET-003", "Jogo de cartas Dupla", "fetiche", 1, 4490, 1500, 30, 5, 110, "9504.90.90", False,
     "100 cartas com desafios para dois.",
     "Baralho com desafios em três níveis — do romântico ao ousado. Para abrir conversa e descobrir vontades."),
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
    for cupom in (Cupom(codigo="VOLTA10", tipo="percentual", valor=10, minimo_cents=5000), Cupom(codigo="BEMVINDO", tipo="fixo", valor=1500, minimo_cents=9900)):
        if not db.execute(select(Cupom).where(Cupom.codigo == cupom.codigo)).first():
            db.add(cupom)
    frete.garantir_tabela(db)
    db.flush()
    return True
