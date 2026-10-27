"""Assistente opcional (API da Claude): escreve descrição de produto e sugere resposta de pós-venda.

Só funciona com ANTHROPIC_API_KEY no .env. Sem a chave, os botões do painel ficam ocultos.
"""
from __future__ import annotations

from ..config import config

TOM = (
    "Você escreve para uma sex shop online brasileira voltada a homens gays e bissexuais. "
    "Tom: adulto, direto, acolhedor e sem vergonha — sexo é natural, não é sujo. Nada de vulgaridade gratuita, "
    "nada de promessas médicas, nada de clichês de propaganda. Português do Brasil, frases curtas."
)


def disponivel() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _perguntar(instrucao: str, conteudo: str, max_tokens: int = 600) -> str:
    if not disponivel():
        raise RuntimeError("Assistente desligado: defina ANTHROPIC_API_KEY no .env.")
    import httpx

    resposta = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": config.MODELO_ASSISTENTE, "max_tokens": max_tokens, "system": TOM + " " + instrucao, "messages": [{"role": "user", "content": conteudo}]},
        timeout=60,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    return "".join(bloco.get("text", "") for bloco in dados.get("content", []) if bloco.get("type") == "text").strip()


def descrever_produto(nome: str, categoria: str, notas: str = "") -> dict:
    texto = _perguntar(
        "Escreva um resumo de até 90 caracteres e uma descrição de 2 a 4 frases para a página do produto. "
        "Responda exatamente neste formato:\nRESUMO: ...\nDESCRIÇÃO: ...",
        f"Produto: {nome}\nCategoria: {categoria}\nObservações do lojista: {notas or '-'}",
    )
    resumo, descricao = "", texto
    for linha in texto.splitlines():
        if linha.upper().startswith("RESUMO:"):
            resumo = linha.split(":", 1)[1].strip()
        elif linha.upper().startswith("DESCRIÇÃO:") or linha.upper().startswith("DESCRICAO:"):
            descricao = linha.split(":", 1)[1].strip()
    return {"resumo": resumo[:200], "descricao": descricao}


def sugerir_resposta_ticket(tipo: str, assunto: str, historico: str, politica: str) -> str:
    return _perguntar(
        "Sugira a resposta da loja ao cliente, em primeira pessoa do singular (a loja é operada por uma pessoa só). "
        "Resolva o que der para resolver, seja claro sobre prazos e sobre a política de trocas. Até 6 frases.",
        f"Tipo: {tipo}\nAssunto: {assunto}\nPolítica da loja: {politica}\n\nConversa até agora:\n{historico}",
    )
