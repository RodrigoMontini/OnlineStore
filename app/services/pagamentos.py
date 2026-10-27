"""PIX: gera o 'copia e cola' (BR Code) e o QR. A confirmação é manual no painel
ou por webhook (quando um PSP for ligado)."""
from __future__ import annotations

import re

import segno
from sqlalchemy.orm import Session

from ..utils import sem_acentos
from . import configuracoes


def crc16_ccitt(dados: str) -> str:
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _campo(id_: str, valor: str) -> str:
    return f"{id_}{len(valor):02d}{valor}"


def _limpar(texto: str, tamanho: int) -> str:
    t = sem_acentos(texto or "").upper()
    t = re.sub(r"[^A-Z0-9 .\-]", "", t).strip()
    return t[:tamanho] or "LOJA"


def pix_payload(chave: str, nome: str, cidade: str, valor_cents: int | None = None, txid: str = "***", descricao: str = "") -> str:
    """BR Code estático do PIX (padrão EMV/BCB)."""
    chave = (chave or "").strip()
    txid = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:25] or "***"
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    if descricao:
        conta += _campo("02", _limpar(descricao, 40))
    payload = _campo("00", "01") + _campo("26", conta) + _campo("52", "0000") + _campo("53", "986")
    if valor_cents and valor_cents > 0:
        payload += _campo("54", f"{valor_cents / 100:.2f}")
    payload += _campo("58", "BR") + _campo("59", _limpar(nome, 25)) + _campo("60", _limpar(cidade, 15))
    payload += _campo("62", _campo("05", txid))
    payload += "6304"
    return payload + crc16_ccitt(payload)


def qr_svg_data_uri(payload: str) -> str:
    qr = segno.make(payload, error="M")
    return qr.svg_data_uri(scale=6, border=2, dark="#141a33")


def gerar_para_pedido(db: Session, numero_pedido: str, total_cents: int) -> tuple[str, str]:
    """Retorna (txid, payload). Sem chave PIX configurada, payload vazio (o painel avisa)."""
    chave = configuracoes.obter(db, "pix_chave")
    if not chave:
        return "", ""
    nome = configuracoes.obter(db, "pix_nome") or configuracoes.obter(db, "loja_nome")
    cidade = configuracoes.obter(db, "pix_cidade") or "SAO PAULO"
    txid = re.sub(r"[^A-Za-z0-9]", "", numero_pedido)
    return txid, pix_payload(chave, nome, cidade, total_cents, txid=txid)
