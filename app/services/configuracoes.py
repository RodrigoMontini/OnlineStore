"""Configurações da loja guardadas no banco (editáveis pelo painel)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Configuracao

PADROES: dict[str, str] = {
    # Identidade
    "loja_nome": "Pêssego",
    "loja_slogan": "Sexo salva vidas.",
    "loja_manifesto": (
        "Aqui o sexo é para todos e para todes. É um ato natural, faz parte da vida e vem sem culpa "
        "e sem amarras… bom, às vezes com amarras também. "
        "A gente vende o que deixa o sexo mais gostoso, mais seguro e mais seu."
    ),
    "loja_email": "contato@sualoja.com.br",
    "loja_whatsapp": "",  # só números, com DDD. Ex.: 11999990000
    "loja_instagram": "",
    "loja_cidade": "São Paulo",
    "loja_uf": "SP",
    "setup_concluido": "0",
    # PIX
    "pix_chave": "",
    "pix_nome": "",   # nome do recebedor (até 25 caracteres)
    "pix_cidade": "SAO PAULO",
    # Remetente (etiqueta). Nome neutro = embalagem discreta.
    "remetente_nome": "P. Comércio",
    "remetente_logradouro": "",
    "remetente_numero": "",
    "remetente_complemento": "",
    "remetente_bairro": "",
    "remetente_cidade": "São Paulo",
    "remetente_uf": "SP",
    "remetente_cep": "",
    # Frete
    "frete_gratis_acima_cents": "25000",
    "frete_adicional_por_kg_pct": "20",
    "frete_dias_adicionais_processamento": "1",
    # Automações
    "cancelar_nao_pago_horas": "24",
    "cupom_retorno_codigo": "VOLTA10",
    "pos_venda_avaliacao_dias": "3",
    "pos_venda_cupom_dias": "30",
    "nfe_auto_emitir": "0",
    "lead_time_padrao_dias": "7",
    "cobertura_minima_dias": "14",
    # Fiscal / NF-e
    "fiscal_cnpj": "",
    "fiscal_razao_social": "",
    "fiscal_nome_fantasia": "",
    "fiscal_ie": "",
    "fiscal_regime": "1",  # 1 Simples Nacional, 2 Simples excesso sublimite, 3 Regime normal
    "fiscal_logradouro": "",
    "fiscal_numero": "",
    "fiscal_complemento": "",
    "fiscal_bairro": "",
    "fiscal_municipio": "São Paulo",
    "fiscal_codigo_municipio": "3550308",
    "fiscal_uf": "SP",
    "fiscal_cep": "",
    "fiscal_telefone": "",
    "nfe_serie": "1",
    "nfe_proximo_numero": "1",
    "nfe_cfop_dentro_uf": "5102",
    "nfe_cfop_fora_uf": "6102",
    "nfe_csosn": "102",
    "nfe_pis_cst": "49",
    "nfe_cofins_cst": "49",
    "nfe_natureza_operacao": "Venda de mercadoria",
    "nfe_info_complementar": "Documento emitido por ME ou EPP optante pelo Simples Nacional. Não gera direito a crédito fiscal de IPI.",
}


# Textos padrão antigos. Salvar a seção Loja grava o padrão no banco; se continuar
# igual ao antigo, troca pelo novo. Texto escrito à mão no painel não é tocado.
PADROES_ANTIGOS: dict[str, set[str]] = {
    "loja_manifesto": {
        "Uma sex shop para homens que transam com homens. Sexo é safado — e não é sujo, nem demoníaco. "
        "É um ato natural da vida. A gente vende o que ajuda ele a ser mais gostoso, mais seguro e mais seu.",
    },
}


def atualizar_padroes_antigos(db: Session) -> None:
    for chave, antigos in PADROES_ANTIGOS.items():
        linha = db.get(Configuracao, chave)
        if linha is not None and linha.valor.strip() in antigos:
            linha.valor = PADROES[chave]


def obter_todas(db: Session) -> dict[str, str]:
    valores = dict(PADROES)
    for linha in db.query(Configuracao).all():
        valores[linha.chave] = linha.valor
    return valores


def obter(db: Session, chave: str, padrao: str | None = None) -> str:
    linha = db.get(Configuracao, chave)
    if linha is not None:
        return linha.valor
    if padrao is not None:
        return padrao
    return PADROES.get(chave, "")


def obter_int(db: Session, chave: str, padrao: int = 0) -> int:
    try:
        return int(obter(db, chave, str(padrao)) or padrao)
    except ValueError:
        return padrao


def obter_bool(db: Session, chave: str) -> bool:
    return obter(db, chave) in {"1", "true", "sim", "on"}


def definir(db: Session, chave: str, valor: str | int | bool | None) -> None:
    if isinstance(valor, bool):
        valor = "1" if valor else "0"
    valor = "" if valor is None else str(valor)
    linha = db.get(Configuracao, chave)
    if linha is None:
        db.add(Configuracao(chave=chave, valor=valor))
    else:
        linha.valor = valor


def definir_varias(db: Session, valores: dict[str, str | int | bool | None]) -> None:
    for chave, valor in valores.items():
        definir(db, chave, valor)


def proximo_numero_nfe(db: Session) -> int:
    atual = obter_int(db, "nfe_proximo_numero", 1)
    definir(db, "nfe_proximo_numero", atual + 1)
    return atual
