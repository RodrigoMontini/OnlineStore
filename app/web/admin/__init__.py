"""Painel da loja (/admin): tudo que a pessoa que opera a loja precisa, no celular ou no computador."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...security import admin_atual, verificar_csrf
from . import auth, caixa, clientes, compras, configuracoes, estoque, faturamento, hoje, pedidos, posvenda, produtos, relatorios

router = APIRouter(prefix="/admin")
router.include_router(auth.router)

protegido = [Depends(admin_atual), Depends(verificar_csrf)]
for modulo in (hoje, pedidos, compras, estoque, produtos, clientes, posvenda, relatorios, faturamento, caixa, configuracoes):
    router.include_router(modulo.router, dependencies=protegido)
