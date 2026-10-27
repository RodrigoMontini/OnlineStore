"""Esqueceu a senha do painel? Rode no servidor:

    python scripts/resetar_senha.py dono@loja.com.br NovaSenhaForte123
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import sessao  # noqa: E402
from app.models import Admin  # noqa: E402
from app.security import hash_senha  # noqa: E402

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(1)

email, senha = sys.argv[1].strip().lower(), sys.argv[2]
if len(senha) < 8:
    print("Senha com pelo menos 8 caracteres.")
    sys.exit(1)
with sessao() as db:
    admin = db.execute(select(Admin).where(Admin.email == email)).scalar_one_or_none()
    if admin is None:
        admin = Admin(nome="Admin", email=email, senha_hash=hash_senha(senha))
        db.add(admin)
        print(f"Admin {email} criado.")
    else:
        admin.senha_hash = hash_senha(senha)
        print(f"Senha de {email} redefinida.")
