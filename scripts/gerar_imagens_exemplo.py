"""Gera imagens-placeholder (SVG abstratos) para o catálogo de exemplo.

Uso: python scripts/gerar_imagens_exemplo.py
Troque pelas fotos reais no painel (Produtos → editar → imagem).
"""
from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "produtos"

PALETAS = {
    "VIB": ("#F6B58A", "#C9256E", "#2A0F22"),
    "LUB": ("#FBE3D2", "#2F6B4F", "#F6B58A"),
    "PRE": ("#FFF1E8", "#2A0F22", "#C9256E"),
    "BEM": ("#F1E4EC", "#9E1A56", "#F6B58A"),
    "COS": ("#FBE3D2", "#B7791F", "#2A0F22"),
    "ACE": ("#2A0F22", "#F6B58A", "#C9256E"),
    "LIN": ("#C9256E", "#FBE3D2", "#2A0F22"),
}

SKUS = ["VIB-001", "VIB-002", "VIB-003", "VIB-004", "LUB-001", "LUB-002", "LUB-003", "PRE-001", "PRE-002", "BEM-001", "BEM-002", "COS-001", "COS-002", "ACE-001", "ACE-002", "ACE-003", "LIN-001"]


def blob(cx: float, cy: float, r: float, rnd: random.Random, pontos: int = 8) -> str:
    coords = []
    for i in range(pontos):
        ang = 2 * math.pi * i / pontos
        raio = r * rnd.uniform(0.75, 1.15)
        coords.append((cx + raio * math.cos(ang), cy + raio * math.sin(ang)))
    d = f"M {coords[0][0]:.1f} {coords[0][1]:.1f}"
    for i in range(pontos):
        p0 = coords[i]
        p1 = coords[(i + 1) % pontos]
        c1 = (p0[0] + (p1[0] - p0[0]) * 0.3 + rnd.uniform(-12, 12), p0[1] + (p1[1] - p0[1]) * 0.3 + rnd.uniform(-12, 12))
        c2 = (p0[0] + (p1[0] - p0[0]) * 0.7 + rnd.uniform(-12, 12), p0[1] + (p1[1] - p0[1]) * 0.7 + rnd.uniform(-12, 12))
        d += f" C {c1[0]:.1f} {c1[1]:.1f}, {c2[0]:.1f} {c2[1]:.1f}, {p1[0]:.1f} {p1[1]:.1f}"
    return d + " Z"


def gerar(sku: str) -> str:
    fundo, forma, detalhe = PALETAS[sku[:3]]
    rnd = random.Random(int(hashlib.md5(sku.encode()).hexdigest(), 16))
    b1 = blob(300 + rnd.uniform(-60, 60), 300 + rnd.uniform(-60, 60), 180, rnd)
    b2 = blob(300 + rnd.uniform(-120, 120), 300 + rnd.uniform(-120, 120), 70, rnd, 6)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" role="img" aria-label="{sku}">
<rect width="600" height="600" fill="{fundo}"/>
<path d="{b1}" fill="{forma}" opacity="0.95"/>
<path d="{b2}" fill="{detalhe}" opacity="0.9"/>
<text x="32" y="560" font-family="Georgia, serif" font-size="22" fill="{detalhe}" opacity="0.7">{sku}</text>
</svg>
"""


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for sku in SKUS:
        (DESTINO / f"{sku}.svg").write_text(gerar(sku), encoding="utf-8")
    (DESTINO / "placeholder.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600"><rect width="600" height="600" fill="#FBEDE4"/><circle cx="300" cy="300" r="150" fill="#F6B58A"/><text x="300" y="312" text-anchor="middle" font-family="Georgia, serif" font-size="28" fill="#2A0F22">sem foto</text></svg>\n""",
        encoding="utf-8",
    )
    print(f"{len(SKUS) + 1} imagens em {DESTINO}")


if __name__ == "__main__":
    main()
