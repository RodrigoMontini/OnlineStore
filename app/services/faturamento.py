"""Faturamento e NF-e (modelo 55 — a nota usada em venda online com envio).

A loja monta a nota a partir do pedido e manda para um emissor:
  - Focus NFe (https://focusnfe.com.br), quando FOCUS_NFE_TOKEN está no .env;
  - emissor simulado, quando não está: autoriza na hora, gera chave válida e um
    DANFE simplificado — serve para testar o fluxo inteiro sem certificado.

Antes de emitir de verdade: CNPJ, IE, endereço e regime em Configurações →
Fiscal; NCM nos produtos; certificado A1 cadastrado no emissor. Os códigos
tributários padrão (CFOP 5102/6102, CSOSN 102, PIS/COFINS 49) são os mais
comuns para Simples Nacional, mas o contador deve confirmar.
"""
from __future__ import annotations

import json
import random
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import config
from ..models import NotaFiscal, Pedido, StatusNota
from ..utils import CODIGO_UF, agora, so_digitos
from . import configuracoes


class ErroFiscal(Exception):
    pass


# ------------------------------------------------------------------ chave
def digito_verificador_chave(chave43: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = 0
    for i, digito in enumerate(reversed(chave43)):
        soma += int(digito) * pesos[i % 8]
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def montar_chave(uf: str, data: datetime, cnpj: str, serie: int, numero: int, codigo_numerico: int | None = None) -> str:
    cuf = CODIGO_UF.get(uf.upper(), "35")
    aamm = data.strftime("%y%m")
    cnpj = (so_digitos(cnpj) or "0").zfill(14)[-14:]
    cnf = f"{codigo_numerico if codigo_numerico is not None else random.randint(0, 99999999):08d}"
    base = f"{cuf}{aamm}{cnpj}55{serie:03d}{numero:09d}1{cnf}"
    return base + digito_verificador_chave(base)


def chave_valida(chave: str) -> bool:
    d = so_digitos(chave)
    return len(d) == 44 and digito_verificador_chave(d[:43]) == d[43]


# ---------------------------------------------------------------- payload
def dados_fiscais_ok(db: Session) -> list[str]:
    """Lista o que falta para emitir NF-e de verdade."""
    c = configuracoes.obter_todas(db)
    faltas = []
    if len(so_digitos(c["fiscal_cnpj"])) != 14:
        faltas.append("CNPJ do emitente")
    if not c["fiscal_razao_social"]:
        faltas.append("razão social")
    if not c["fiscal_ie"]:
        faltas.append("inscrição estadual")
    for chave, nome in (("fiscal_logradouro", "endereço"), ("fiscal_numero", "número"), ("fiscal_bairro", "bairro"), ("fiscal_municipio", "município"), ("fiscal_cep", "CEP")):
        if not c[chave]:
            faltas.append(nome)
    return faltas


def montar_payload(db: Session, pedido: Pedido, numero: int, serie: int) -> dict:
    c = configuracoes.obter_todas(db)
    dentro_uf = (pedido.uf or "").upper() == (c["fiscal_uf"] or "").upper()
    cfop = c["nfe_cfop_dentro_uf"] if dentro_uf else c["nfe_cfop_fora_uf"]
    itens = []
    desconto_restante = pedido.desconto_cents
    total_itens = sum(i.total_cents for i in pedido.itens) or 1
    for n, item in enumerate(pedido.itens, start=1):
        if n == len(pedido.itens):
            desconto_item = desconto_restante
        else:
            desconto_item = int(round(pedido.desconto_cents * item.total_cents / total_itens))
            desconto_restante -= desconto_item
        produto = item.produto
        itens.append(
            {
                "numero_item": n,
                "codigo_produto": item.sku or str(item.produto_id or n),
                "descricao": item.nome[:120],
                "cfop": cfop,
                "codigo_ncm": (produto.ncm if produto and produto.ncm else "00000000").replace(".", ""),
                "cest": (produto.cest if produto else "") or None,
                "unidade_comercial": (produto.unidade if produto else "UN") or "UN",
                "quantidade_comercial": item.quantidade,
                "valor_unitario_comercial": round(item.preco_unit_cents / 100, 2),
                "unidade_tributavel": (produto.unidade if produto else "UN") or "UN",
                "quantidade_tributavel": item.quantidade,
                "valor_unitario_tributavel": round(item.preco_unit_cents / 100, 2),
                "valor_bruto": round(item.total_cents / 100, 2),
                "valor_desconto": round(desconto_item / 100, 2) if desconto_item else None,
                "icms_origem": (produto.origem if produto else "0") or "0",
                "icms_situacao_tributaria": c["nfe_csosn"],
                "pis_situacao_tributaria": c["nfe_pis_cst"],
                "cofins_situacao_tributaria": c["nfe_cofins_cst"],
                "inclui_no_total": 1,
            }
        )
    payload = {
        "natureza_operacao": c["nfe_natureza_operacao"],
        "data_emissao": agora().strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "tipo_documento": 1,
        "finalidade_emissao": 1,
        "consumidor_final": 1,
        "presenca_comprador": 2,
        "local_destino": 1 if dentro_uf else 2,
        "numero": numero,
        "serie": serie,
        # emitente
        "cnpj_emitente": so_digitos(c["fiscal_cnpj"]),
        "nome_emitente": c["fiscal_razao_social"],
        "nome_fantasia_emitente": c["fiscal_nome_fantasia"] or c["loja_nome"],
        "logradouro_emitente": c["fiscal_logradouro"],
        "numero_emitente": c["fiscal_numero"],
        "complemento_emitente": c["fiscal_complemento"] or None,
        "bairro_emitente": c["fiscal_bairro"],
        "municipio_emitente": c["fiscal_municipio"],
        "uf_emitente": c["fiscal_uf"],
        "cep_emitente": so_digitos(c["fiscal_cep"]),
        "telefone_emitente": so_digitos(c["fiscal_telefone"]) or None,
        "inscricao_estadual_emitente": so_digitos(c["fiscal_ie"]),
        "regime_tributario_emitente": int(c["fiscal_regime"] or 1),
        # destinatário
        "nome_destinatario": pedido.nome,
        "cpf_destinatario": so_digitos(pedido.cpf),
        "telefone_destinatario": so_digitos(pedido.telefone) or None,
        "email_destinatario": pedido.email or None,
        "logradouro_destinatario": pedido.logradouro,
        "numero_destinatario": pedido.numero_end,
        "complemento_destinatario": pedido.complemento or None,
        "bairro_destinatario": pedido.bairro,
        "municipio_destinatario": pedido.cidade,
        "uf_destinatario": pedido.uf,
        "cep_destinatario": so_digitos(pedido.cep),
        "pais_destinatario": "Brasil",
        "indicador_inscricao_estadual_destinatario": 9,
        # totais
        "modalidade_frete": 0 if pedido.frete_cents or pedido.frete_metodo else 9,
        "valor_frete": round(pedido.frete_cents / 100, 2),
        "valor_desconto": round(pedido.desconto_cents / 100, 2),
        "valor_produtos": round(sum(i.total_cents for i in pedido.itens) / 100, 2),
        "valor_total": round(pedido.total_cents / 100, 2),
        "formas_pagamento": [{"forma_pagamento": "17", "valor_pagamento": round(pedido.total_cents / 100, 2)}],
        "informacoes_adicionais_contribuinte": f"Pedido {pedido.numero}. {c['nfe_info_complementar']}".strip(),
        "items": itens,
    }
    return {k: v for k, v in payload.items() if v is not None}


# -------------------------------------------------------------- provedores
class ProvedorSimulado:
    nome = "simulado"
    ambiente = "simulado"

    def emitir(self, db: Session, nota: NotaFiscal, payload: dict) -> dict:
        chave = montar_chave(payload.get("uf_emitente") or "SP", agora(), payload.get("cnpj_emitente", ""), nota.serie, nota.numero)
        return {
            "status": StatusNota.AUTORIZADA,
            "chave": chave,
            "protocolo": f"SIM{agora().strftime('%Y%m%d%H%M%S')}{nota.numero:05d}",
            "xml_url": "",
            "danfe_url": f"/admin/faturamento/{nota.id}/danfe",
            "mensagem": "Autorizada pelo emissor simulado (sem valor fiscal).",
        }

    def consultar(self, db: Session, nota: NotaFiscal) -> dict:
        return {"status": nota.status, "mensagem": nota.mensagem}

    def cancelar(self, db: Session, nota: NotaFiscal, justificativa: str) -> dict:
        return {"status": StatusNota.CANCELADA, "mensagem": "Cancelada no emissor simulado."}


class ProvedorFocusNFe:
    nome = "focusnfe"

    def __init__(self, token: str, ambiente: str = "homologacao"):
        self.token = token
        self.ambiente = "producao" if ambiente == "producao" else "homologacao"
        self.base = "https://api.focusnfe.com.br" if self.ambiente == "producao" else "https://homologacao.focusnfe.com.br"

    def _http(self):
        import httpx

        return httpx.Client(base_url=self.base, auth=(self.token, ""), timeout=40)

    @staticmethod
    def _traduzir(resposta: dict) -> dict:
        status = resposta.get("status", "")
        mapa = {
            "autorizado": StatusNota.AUTORIZADA,
            "processando_autorizacao": StatusNota.PROCESSANDO,
            "cancelado": StatusNota.CANCELADA,
            "erro_autorizacao": StatusNota.ERRO,
            "denegado": StatusNota.ERRO,
        }
        mensagem = resposta.get("mensagem_sefaz") or resposta.get("mensagem") or ""
        if resposta.get("erros"):
            mensagem = "; ".join(f"{e.get('campo', '')}: {e.get('mensagem', '')}".strip(": ") for e in resposta["erros"])
        chave = (resposta.get("chave_nfe") or "").replace("NFe", "")
        return {
            "status": mapa.get(status, StatusNota.PROCESSANDO if status else StatusNota.ERRO),
            "chave": chave,
            "protocolo": str(resposta.get("protocolo") or ""),
            "xml_url": (self.base + resposta["caminho_xml_nota_fiscal"]) if resposta.get("caminho_xml_nota_fiscal") else "",
            "danfe_url": (self.base + resposta["caminho_danfe"]) if resposta.get("caminho_danfe") else "",
            "mensagem": mensagem[:1000],
        }

    def emitir(self, db: Session, nota: NotaFiscal, payload: dict) -> dict:
        with self._http() as http:
            r = http.post(f"/v2/nfe", params={"ref": nota.referencia}, json=payload)
            try:
                corpo = r.json()
            except ValueError:
                corpo = {"status": "erro_autorizacao", "mensagem": f"HTTP {r.status_code}: {r.text[:300]}"}
            if r.status_code >= 400 and "status" not in corpo:
                corpo = {"status": "erro_autorizacao", "mensagem": corpo.get("mensagem") or f"HTTP {r.status_code}", "erros": corpo.get("erros")}
            return self._traduzir(corpo)

    def consultar(self, db: Session, nota: NotaFiscal) -> dict:
        with self._http() as http:
            r = http.get(f"/v2/nfe/{nota.referencia}", params={"completa": 0})
            try:
                return self._traduzir(r.json())
            except ValueError:
                return {"status": StatusNota.ERRO, "mensagem": f"HTTP {r.status_code}"}

    def cancelar(self, db: Session, nota: NotaFiscal, justificativa: str) -> dict:
        with self._http() as http:
            r = http.request("DELETE", f"/v2/nfe/{nota.referencia}", json={"justificativa": justificativa[:255]})
            try:
                corpo = r.json()
            except ValueError:
                corpo = {"status": "erro", "mensagem": f"HTTP {r.status_code}"}
            if corpo.get("status") == "cancelado":
                return {"status": StatusNota.CANCELADA, "mensagem": "Cancelamento autorizado."}
            return {"status": nota.status, "mensagem": corpo.get("mensagem") or "Não foi possível cancelar."}


def provedor():
    if config.FOCUS_NFE_TOKEN:
        return ProvedorFocusNFe(config.FOCUS_NFE_TOKEN, config.FOCUS_NFE_AMBIENTE)
    return ProvedorSimulado()


def modo() -> dict:
    p = provedor()
    return {"nome": p.nome, "ambiente": p.ambiente, "simulado": p.nome == "simulado"}


# ------------------------------------------------------------------ ações
def _aplicar(nota: NotaFiscal, resultado: dict) -> None:
    nota.status = resultado.get("status", nota.status)
    nota.chave = resultado.get("chave") or nota.chave
    nota.protocolo = resultado.get("protocolo") or nota.protocolo
    nota.xml_url = resultado.get("xml_url") or nota.xml_url
    nota.danfe_url = resultado.get("danfe_url") or nota.danfe_url
    nota.mensagem = resultado.get("mensagem") or nota.mensagem
    if nota.status == StatusNota.AUTORIZADA and not nota.emitida_em:
        nota.emitida_em = agora()
    if nota.status == StatusNota.CANCELADA and not nota.cancelada_em:
        nota.cancelada_em = agora()


def emitir(db: Session, pedido: Pedido) -> NotaFiscal:
    if not pedido.pago:
        raise ErroFiscal("Só pedidos pagos geram NF-e.")
    atual = pedido.nota_atual
    if atual and atual.status in {StatusNota.AUTORIZADA, StatusNota.PROCESSANDO}:
        raise ErroFiscal(f"Pedido já tem NF-e {atual.numero} ({atual.label}).")
    if not so_digitos(pedido.cpf):
        raise ErroFiscal("Pedido sem CPF do destinatário.")
    p = provedor()
    if p.nome != "simulado":
        faltas = dados_fiscais_ok(db)
        if faltas:
            raise ErroFiscal("Preencha em Configurações → Fiscal: " + ", ".join(faltas) + ".")
        sem_ncm = [i.nome for i in pedido.itens if i.produto and not i.produto.ncm]
        if sem_ncm:
            raise ErroFiscal("Produtos sem NCM: " + ", ".join(sem_ncm))
    if atual and atual.status == StatusNota.ERRO:
        nota = atual  # reaproveita número e referência
    else:
        serie = configuracoes.obter_int(db, "nfe_serie", 1)
        numero = configuracoes.proximo_numero_nfe(db)
        nota = NotaFiscal(pedido_id=pedido.id, numero=numero, serie=serie, provedor=p.nome, ambiente=p.ambiente, valor_cents=pedido.total_cents)
        db.add(nota)
        db.flush()
        nota.referencia = f"{pedido.numero}-{nota.id}"
    payload = montar_payload(db, pedido, nota.numero, nota.serie)
    nota.payload_json = json.dumps(payload, ensure_ascii=False)
    nota.status = StatusNota.PROCESSANDO
    nota.mensagem = ""
    try:
        resultado = p.emitir(db, nota, payload)
    except Exception as exc:  # rede, timeout...
        resultado = {"status": StatusNota.ERRO, "mensagem": f"Falha ao falar com o emissor: {exc}"[:500]}
    _aplicar(nota, resultado)
    db.flush()
    return nota


def consultar(db: Session, nota: NotaFiscal) -> NotaFiscal:
    p = provedor()
    if nota.provedor != p.nome:
        return nota
    try:
        _aplicar(nota, p.consultar(db, nota))
    except Exception as exc:
        nota.mensagem = f"Falha ao consultar: {exc}"[:500]
    db.flush()
    return nota


def cancelar(db: Session, nota: NotaFiscal, justificativa: str) -> NotaFiscal:
    if nota.status != StatusNota.AUTORIZADA:
        raise ErroFiscal("Só notas autorizadas podem ser canceladas.")
    justificativa = (justificativa or "").strip()
    if len(justificativa) < 15:
        raise ErroFiscal("A justificativa precisa ter pelo menos 15 caracteres.")
    p = provedor()
    resultado = p.cancelar(db, nota, justificativa)
    nota.justificativa = justificativa[:300]
    _aplicar(nota, resultado)
    db.flush()
    if nota.status != StatusNota.CANCELADA:
        raise ErroFiscal(nota.mensagem or "O emissor não aceitou o cancelamento.")
    return nota


def pendentes(db: Session) -> list[Pedido]:
    """Pedidos pagos sem NF-e autorizada (para o painel 'Hoje')."""
    from ..models import StatusPedido

    pedidos = db.execute(select(Pedido).where(Pedido.status.in_(StatusPedido.PAGOS)).order_by(Pedido.pago_em)).scalars()
    return [p for p in pedidos if p.status != StatusPedido.DEVOLVIDO and not (p.nota_atual and p.nota_atual.status in {StatusNota.AUTORIZADA, StatusNota.PROCESSANDO})]


def listar(db: Session, status: str | None = None, inicio=None, fim=None, limite: int = 500) -> list[NotaFiscal]:
    q = select(NotaFiscal).order_by(NotaFiscal.id.desc()).limit(limite)
    if status:
        q = q.where(NotaFiscal.status == status)
    if inicio:
        q = q.where(NotaFiscal.criado_em >= inicio.strftime("%Y-%m-%d 00:00:00"))
    if fim:
        q = q.where(NotaFiscal.criado_em <= fim.strftime("%Y-%m-%d 23:59:59"))
    return list(db.execute(q).scalars())


def faturamento_por_mes(db: Session, meses: int = 12) -> list[dict]:
    linhas = db.execute(
        select(func.strftime("%Y-%m", NotaFiscal.emitida_em), func.count(NotaFiscal.id), func.sum(NotaFiscal.valor_cents))
        .where(NotaFiscal.status == StatusNota.AUTORIZADA)
        .group_by(func.strftime("%Y-%m", NotaFiscal.emitida_em))
        .order_by(func.strftime("%Y-%m", NotaFiscal.emitida_em).desc())
        .limit(meses)
    ).all()
    return [{"mes": m, "notas": int(n), "total_cents": int(t or 0)} for m, n, t in linhas if m]
