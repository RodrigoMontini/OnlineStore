"""Conexão com o banco (SQLite) e sessão do SQLAlchemy."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import config


class Base(DeclarativeBase):
    pass


def _criar_engine():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{config.DB_PATH}",
        connect_args={"check_same_thread": False, "timeout": 30},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(conexao, _registro):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


engine = _criar_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por requisição."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def sessao() -> Iterator[Session]:
    """Uso fora de requisições (automações, scripts, testes)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
