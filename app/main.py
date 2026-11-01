"""Aplicação web: vitrine + painel + API, num único processo."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import models  # noqa: F401  (registra as tabelas)
from .config import config
from .db import Base, engine, sessao
from .security import NaoAutenticado
from .services import automacoes, catalogo, configuracoes
from .web import api, loja
from .web.admin import router as admin_router

log = logging.getLogger("loja")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def preparar_banco() -> None:
    Base.metadata.create_all(engine)
    with sessao() as db:
        if catalogo.seed_se_vazio(db):
            log.info("Catálogo de exemplo carregado.")
        configuracoes.atualizar_padroes_antigos(db)
        try:
            automacoes.executar(db)
        except Exception:  # pragma: no cover
            log.exception("Falha nas automações iniciais")


async def _laco_automacoes(intervalo_s: int = 600) -> None:
    while True:
        await asyncio.sleep(intervalo_s)
        try:
            with sessao() as db:
                automacoes.executar(db)
        except Exception:  # pragma: no cover
            log.exception("Falha nas automações")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    preparar_banco()
    tarefa = asyncio.create_task(_laco_automacoes())
    try:
        yield
    finally:
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa


def criar_app() -> FastAPI:
    app = FastAPI(title="Loja", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SECRET_KEY,
        session_cookie="sessao",
        same_site="lax",
        https_only=config.BASE_URL.startswith("https://"),
        max_age=60 * 60 * 24 * 30,
    )
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/media", StaticFiles(directory=str(config.UPLOAD_DIR)), name="media")

    @app.exception_handler(NaoAutenticado)
    async def _redirecionar_login(request: Request, exc: NaoAutenticado):
        return RedirectResponse(f"/admin/login?next={exc.destino}", status_code=303)

    app.include_router(loja.router)
    app.include_router(api.router)
    app.include_router(admin_router)
    return app


app = criar_app()
