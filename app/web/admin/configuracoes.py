"""Configurações: loja, PIX, remetente, frete, cupons, fiscal, automações, senha."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Admin, Cupom, TabelaFrete
from ...security import admin_atual, flash, hash_senha, verificar_senha
from ...services import configuracoes as svc, frete
from ...utils import NOME_REGIAO, parse_dinheiro, so_digitos
from ..render import render

router = APIRouter(prefix="/configuracoes")

SECOES = {
    "loja": ["loja_nome", "loja_slogan", "loja_manifesto", "loja_email", "loja_whatsapp", "loja_instagram", "loja_cidade", "loja_uf"],
    "pix": ["pix_chave", "pix_nome", "pix_cidade"],
    "remetente": ["remetente_nome", "remetente_logradouro", "remetente_numero", "remetente_complemento", "remetente_bairro", "remetente_cidade", "remetente_uf", "remetente_cep"],
    "automacoes": ["cancelar_nao_pago_horas", "cupom_retorno_codigo", "pos_venda_avaliacao_dias", "pos_venda_cupom_dias", "nfe_auto_emitir", "lead_time_padrao_dias", "cobertura_minima_dias"],
    "fiscal": [
        "fiscal_cnpj", "fiscal_razao_social", "fiscal_nome_fantasia", "fiscal_ie", "fiscal_regime", "fiscal_logradouro", "fiscal_numero", "fiscal_complemento",
        "fiscal_bairro", "fiscal_municipio", "fiscal_codigo_municipio", "fiscal_uf", "fiscal_cep", "fiscal_telefone", "nfe_serie", "nfe_proximo_numero",
        "nfe_cfop_dentro_uf", "nfe_cfop_fora_uf", "nfe_csosn", "nfe_pis_cst", "nfe_cofins_cst", "nfe_natureza_operacao", "nfe_info_complementar",
    ],
}


@router.get("")
def pagina(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/configuracoes.html", db, cfg=svc.obter_todas(db), tabela=frete.tabela(db), regioes=NOME_REGIAO, cupons=db.query(Cupom).order_by(Cupom.id.desc()).all(), frete_gratis=svc.obter_int(db, "frete_gratis_acima_cents"))


@router.post("/{secao}")
async def salvar(request: Request, secao: str, db: Session = Depends(get_db), admin: Admin = Depends(admin_atual)):
    form = await request.form()
    if secao in SECOES:
        valores = {}
        for chave in SECOES[secao]:
            if chave == "nfe_auto_emitir":
                valores[chave] = "1" if form.get(chave) else "0"
            else:
                valores[chave] = (form.get(chave) or "").strip()
        if secao == "loja":
            valores["loja_whatsapp"] = so_digitos(valores["loja_whatsapp"])
        if secao == "fiscal":
            valores["fiscal_cnpj"] = so_digitos(valores["fiscal_cnpj"])
            valores["fiscal_cep"] = so_digitos(valores["fiscal_cep"])
        svc.definir_varias(db, valores)
        db.commit()
        flash(request, "Configurações salvas.")
    elif secao == "frete":
        svc.definir(db, "frete_gratis_acima_cents", parse_dinheiro(form.get("frete_gratis_acima")))
        svc.definir(db, "frete_adicional_por_kg_pct", int(form.get("frete_adicional_por_kg_pct") or 20))
        svc.definir(db, "frete_dias_adicionais_processamento", int(form.get("frete_dias_adicionais_processamento") or 1))
        for linha in frete.tabela(db):
            preco = form.get(f"preco_{linha.id}")
            prazo = form.get(f"prazo_{linha.id}")
            if preco is not None:
                linha.preco_cents = parse_dinheiro(preco)
            if prazo:
                linha.prazo_dias = int(prazo)
            linha.ativo = form.get(f"ativo_{linha.id}") == "1"
        db.commit()
        flash(request, "Tabela de frete salva.")
    elif secao == "cupom":
        codigo = (form.get("codigo") or "").strip().upper()
        if codigo:
            cupom = db.query(Cupom).filter(Cupom.codigo == codigo).first() or Cupom(codigo=codigo)
            cupom.tipo = form.get("tipo") or "percentual"
            cupom.valor = int(form.get("valor") or 10) if cupom.tipo == "percentual" else parse_dinheiro(form.get("valor"))
            cupom.minimo_cents = parse_dinheiro(form.get("minimo"))
            cupom.max_usos = int(form.get("max_usos") or 0)
            cupom.ativo = form.get("ativo", "1") == "1"
            cupom.validade = date.fromisoformat(form["validade"]) if form.get("validade") else None
            db.add(cupom)
            db.commit()
            flash(request, f"Cupom {codigo} salvo.")
    elif secao == "cupom_remover":
        cupom = db.get(Cupom, int(form.get("id")))
        if cupom:
            cupom.ativo = False
            db.commit()
    elif secao == "senha":
        atual, nova, nova2 = form.get("senha_atual") or "", form.get("senha_nova") or "", form.get("senha_nova2") or ""
        if not verificar_senha(atual, admin.senha_hash):
            flash(request, "Senha atual não confere.", "erro")
        elif len(nova) < 8 or nova != nova2:
            flash(request, "A nova senha precisa ter 8+ caracteres e ser igual nos dois campos.", "erro")
        else:
            admin.senha_hash = hash_senha(nova)
            db.commit()
            flash(request, "Senha alterada.")
    return RedirectResponse(f"/admin/configuracoes#{secao.split('_')[0]}", status_code=303)
