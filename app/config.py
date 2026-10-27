"""Configuração por variáveis de ambiente (arquivo .env) e caminhos de dados.

Tudo que é específico da loja (nome, PIX, frete, dados fiscais) fica no banco,
na tabela `configuracoes`, e é editado pelo painel. Aqui ficam só os segredos
e os caminhos da instalação.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(valor: str | None, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


class Config:
    DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "loja.db"))
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DATA_DIR / "uploads"))
    PORT = int(os.getenv("PORT", "8000"))
    BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}").rstrip("/")
    DEBUG = _bool(os.getenv("DEBUG"), False)
    FUSO = os.getenv("FUSO_HORARIO", "America/Sao_Paulo")

    # Emissor de NF-e (Focus NFe). Sem token, a loja usa o emissor simulado.
    FOCUS_NFE_TOKEN = os.getenv("FOCUS_NFE_TOKEN", "").strip()
    FOCUS_NFE_AMBIENTE = os.getenv("FOCUS_NFE_AMBIENTE", "homologacao").strip()  # homologacao | producao

    # E-mail transacional (opcional). Sem SMTP, as mensagens ficam na caixa de saída do painel.
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
    SMTP_FROM = os.getenv("SMTP_FROM", "").strip()

    # Assistente opcional (descrições de produto e respostas de pós-venda).
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    MODELO_ASSISTENTE = os.getenv("MODELO_ASSISTENTE", "claude-sonnet-5-5").strip()

    # Token do webhook de pagamento (para ligar um PSP depois).
    WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()

    _secret: str | None = os.getenv("SECRET_KEY")

    @property
    def SECRET_KEY(self) -> str:
        """Chave de assinatura dos cookies. Gerada uma vez e guardada em data/secret.key."""
        if self._secret:
            return self._secret
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        arquivo = self.DATA_DIR / "secret.key"
        if arquivo.exists():
            self._secret = arquivo.read_text().strip()
        else:
            self._secret = secrets.token_urlsafe(48)
            arquivo.write_text(self._secret)
        return self._secret


config = Config()
