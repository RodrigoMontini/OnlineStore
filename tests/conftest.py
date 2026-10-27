import os
import re
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="loja-teste-"))
os.environ["DATA_DIR"] = str(_tmp)
os.environ["DB_PATH"] = str(_tmp / "loja.db")
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["SECRET_KEY"] = "teste-nao-use-em-producao"
os.environ["WEBHOOK_TOKEN"] = "segredo-webhook"
os.environ.pop("FOCUS_NFE_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def cliente():
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def csrf_de(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html) or re.search(r'<meta name="csrf" content="([^"]+)"', html)
    assert m, "token csrf não encontrado na página"
    return m.group(1)


@pytest.fixture(scope="session")
def admin(cliente):
    """Cria o admin pelo setup e devolve um cliente autenticado (mesma sessão/cookies)."""
    r = cliente.get("/admin/setup")
    assert r.status_code == 200
    token = csrf_de(r.text)
    r = cliente.post(
        "/admin/setup",
        data={"csrf": token, "nome": "Rodrigo", "email": "dono@loja.test", "senha": "senha-forte-123", "senha2": "senha-forte-123", "loja_nome": "Loja Teste", "pix_chave": "dono@loja.test", "pix_nome": "Loja Teste", "loja_whatsapp": "11999990000"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return cliente
