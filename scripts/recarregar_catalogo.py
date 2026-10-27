"""Troca o catálogo de exemplo pelo catálogo atual do código (só enquanto não há pedidos).

    python scripts/recarregar_catalogo.py

Mantém admin, configurações e tabela de frete. Apaga produtos, categorias, fornecedores,
compras e movimentos de estoque de exemplo e carrega os novos.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db import Base, engine, sessao  # noqa: E402
from app.models import Avaliacao, Categoria, Compra, CompraItem, Fornecedor, MovimentoEstoque, Pedido, Produto  # noqa: E402
from app.services import catalogo  # noqa: E402

Base.metadata.create_all(engine)
with sessao() as db:
    if db.execute(select(Pedido.id).limit(1)).first():
        print("Já existem pedidos: não vou apagar o catálogo. Edite os produtos pelo painel.")
        sys.exit(1)
    for tabela in (Avaliacao, MovimentoEstoque, CompraItem, Compra, Produto, Categoria, Fornecedor):
        db.execute(delete(tabela))
    db.flush()
    catalogo.seed_se_vazio(db)
    print("Catálogo recarregado.")
