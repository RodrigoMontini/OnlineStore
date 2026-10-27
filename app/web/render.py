"""Renderização dos templates com os filtros e variáveis que toda página usa."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from sqlalchemy.orm import Session

from ..models import StatusCompra, StatusNota, StatusPedido, TipoFollowUp, TipoTicket
from ..security import consumir_flash, csrf_token
from ..services import assistente, catalogo, configuracoes, faturamento
from ..utils import brl, fmt_cep, fmt_cnpj, fmt_cpf, fmt_data, fmt_datahora, fmt_relativo, fmt_telefone, hoje

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _nl2br(texto: str | None) -> Markup:
    if not texto:
        return Markup("")
    return Markup("<br>".join(str(escape(linha)) for linha in str(texto).splitlines()))


def _estrelas(nota: float | int) -> str:
    cheias = int(round(float(nota or 0)))
    return "★" * cheias + "☆" * (5 - cheias)


templates.env.filters.update(
    brl=brl,
    data=fmt_data,
    datahora=fmt_datahora,
    relativo=fmt_relativo,
    cpf=fmt_cpf,
    cnpj=fmt_cnpj,
    cep=fmt_cep,
    telefone=fmt_telefone,
    nl2br=_nl2br,
    estrelas=_estrelas,
)
templates.env.globals.update(
    StatusPedido=StatusPedido,
    StatusCompra=StatusCompra,
    StatusNota=StatusNota,
    TipoFollowUp=TipoFollowUp,
    TipoTicket=TipoTicket,
    hoje=hoje,
)


def render(request: Request, nome: str, db: Session, status_code: int = 200, **contexto):
    carrinho = request.session.get("carrinho") or {}
    contexto.setdefault("loja", configuracoes.obter_todas(db))
    contexto.update(
        request=request,
        flashes=consumir_flash(request),
        csrf=csrf_token(request),
        carrinho_qtd=sum(int(q) for q in carrinho.values()),
        categorias_menu=catalogo.categorias(db),
        assistente_ativo=assistente.disponivel(),
        nfe_modo=faturamento.modo(),
        admin_logado=bool(request.session.get("admin_id")),
    )
    return templates.TemplateResponse(request, nome, contexto, status_code=status_code)
