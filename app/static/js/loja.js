/* Vitrine: porta 18+, menu, quantidade, CEP/frete no checkout, copiar PIX. */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  // Porta 18+
  const porta = $("#porta18");
  if (porta) {
    let ok = false;
    try { ok = localStorage.getItem("maior18") === "1"; } catch (e) {}
    if (ok) porta.hidden = true;
    else document.body.style.overflow = "hidden";
    $("#porta-sim", porta).addEventListener("click", () => {
      try { localStorage.setItem("maior18", "1"); } catch (e) {}
      porta.hidden = true;
      document.body.style.overflow = "";
    });
  }

  // Menu mobile
  const btnMenu = $("#menu-btn");
  if (btnMenu) btnMenu.addEventListener("click", () => {
    const m = $("#menu-mobile");
    const aberto = m.classList.toggle("aberto");
    btnMenu.setAttribute("aria-expanded", aberto ? "true" : "false");
  });

  // Quantidade
  $$(".qtd").forEach((box) => {
    const input = $("input", box);
    $$("button", box).forEach((b) => b.addEventListener("click", () => {
      const max = parseInt(input.max || "99", 10);
      let v = parseInt(input.value || "1", 10) + (b.dataset.d === "+" ? 1 : -1);
      input.value = Math.max(1, Math.min(max, v));
      if (box.closest("form") && box.dataset.auto) box.closest("form").requestSubmit();
    }));
  });

  // Copiar
  $$("[data-copiar]").forEach((b) => b.addEventListener("click", async () => {
    const alvo = $(b.dataset.copiar);
    const texto = alvo ? (alvo.value || alvo.textContent) : b.dataset.texto;
    try { await navigator.clipboard.writeText(texto); b.textContent = b.dataset.feito || "Copiado"; }
    catch (e) { if (alvo && alvo.select) { alvo.select(); document.execCommand("copy"); b.textContent = "Copiado"; } }
    setTimeout(() => (b.textContent = b.dataset.rotulo || "Copiar"), 2000);
  }));

  // Home: título entra depois da porta 18+, aura segue o ponteiro, prévia do índice, peças inclinam, seções revelam
  const calmo = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fino = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const capa = $(".capa");
  if (capa) {
    const iniciar = () => capa.classList.add("ativa");
    if (calmo) $$("svg", capa).forEach((s) => s.pauseAnimations && s.pauseAnimations());
    else if (!porta || porta.hidden) iniciar();
    else $("#porta-sim").addEventListener("click", iniciar);

    if (fino && !calmo) {
      let x = 0.7, y = 0.4, ax = x, ay = y, rodando = false;
      const passo = () => {
        ax += (x - ax) * 0.08; ay += (y - ay) * 0.08;
        capa.style.setProperty("--ax", (ax * 100).toFixed(2) + "%");
        capa.style.setProperty("--ay", (ay * 100).toFixed(2) + "%");
        rodando = Math.abs(x - ax) + Math.abs(y - ay) > 0.001;
        if (rodando) requestAnimationFrame(passo);
      };
      capa.addEventListener("pointermove", (e) => {
        const r = capa.getBoundingClientRect();
        x = (e.clientX - r.left) / r.width; y = (e.clientY - r.top) / r.height;
        if (!rodando) { rodando = true; requestAnimationFrame(passo); }
      });
    }
  }

  const indice = $(".indice");
  const previa = $(".indice-previa");
  if (indice && previa && fino) {
    const img = $("img", previa);
    let px = 0, py = 0, vx = 0, vy = 0, raf = 0;
    const seguir = () => {
      const k = calmo ? 1 : 0.18;
      vx += (px - vx) * k; vy += (py - vy) * k;
      const giro = calmo ? 0 : Math.max(-12, Math.min(12, (px - vx) * 0.08));
      previa.style.transform = `translate(${vx}px, ${vy}px) translate(28px, -50%) rotate(${giro}deg)`;
      raf = Math.abs(px - vx) + Math.abs(py - vy) > 0.5 ? requestAnimationFrame(seguir) : 0;
    };
    indice.addEventListener("pointerenter", (e) => { px = vx = e.clientX; py = vy = e.clientY; seguir(); });
    indice.addEventListener("pointermove", (e) => { px = e.clientX; py = e.clientY; if (!raf) raf = requestAnimationFrame(seguir); });
    $$(".indice-item", indice).forEach((item) => {
      item.addEventListener("pointerenter", () => { img.src = item.dataset.capa; previa.classList.add("visivel"); });
      item.addEventListener("pointerleave", () => previa.classList.remove("visivel"));
    });
  }

  if (fino && !calmo) $$(".peca").forEach((peca) => {
    peca.addEventListener("pointermove", (e) => {
      const r = peca.getBoundingClientRect();
      const dx = (e.clientX - r.left) / r.width - 0.5, dy = (e.clientY - r.top) / r.height - 0.5;
      peca.style.setProperty("--rx", (-dy * 8).toFixed(2) + "deg");
      peca.style.setProperty("--ry", (dx * 10).toFixed(2) + "deg");
      peca.style.setProperty("--lx", ((dx + 0.5) * 100).toFixed(1) + "%");
      peca.style.setProperty("--ly", ((dy + 0.5) * 100).toFixed(1) + "%");
    });
    peca.addEventListener("pointerleave", () => ["--rx", "--ry"].forEach((v) => peca.style.removeProperty(v)));
  });

  const revelar = $$("[data-revelar]");
  if (revelar.length && "IntersectionObserver" in window && !calmo) {
    document.documentElement.classList.add("revela");
    const io = new IntersectionObserver((entradas) => entradas.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add("visto"); io.unobserve(en.target); }
    }), { rootMargin: "0px 0px -12% 0px" });
    revelar.forEach((el) => io.observe(el));
  }

  // Checkout: CEP, frete, cupom
  const form = $("#form-checkout");
  if (!form) return;
  const cep = $("#cep");
  const caixaFrete = $("#opcoes-frete");
  const fmt = (c) => "R$ " + (c / 100).toFixed(2).replace(".", ",");
  const subtotal = parseInt(form.dataset.subtotal || "0", 10);
  let desconto = 0;

  function atualizarTotal() {
    const sel = $("input[name=frete_metodo]:checked");
    const frete = sel ? parseInt(sel.dataset.preco || "0", 10) : 0;
    const tipoCupom = form.dataset.tipoCupom || "";
    const freteFinal = tipoCupom === "frete" ? 0 : frete;
    $("#res-frete").textContent = sel ? (freteFinal === 0 ? "Grátis" : fmt(freteFinal)) : "—";
    $("#res-desconto").textContent = desconto ? "- " + fmt(desconto) : "—";
    $("#res-total").textContent = fmt(subtotal - desconto + freteFinal);
  }

  async function cotarFrete() {
    const d = (cep.value || "").replace(/\D/g, "");
    if (d.length !== 8) return;
    caixaFrete.innerHTML = '<p class="ajuda">Calculando frete…</p>';
    try {
      const r = await fetch("/api/frete?cep=" + d, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.ok) { caixaFrete.innerHTML = '<p class="msg-erro">' + (j.erro || "CEP não atendido") + "</p>"; return; }
      const atual = form.dataset.freteSelecionado || "";
      caixaFrete.innerHTML = j.opcoes.map((o, i) => `
        <label class="opcao-frete">
          <input type="radio" name="frete_metodo" value="${o.metodo}" data-preco="${o.preco_cents}" ${(atual ? atual === o.metodo : i === 0) ? "checked" : ""}>
          <span><strong>${o.metodo}</strong><br><small>até ${o.prazo_dias} dias úteis · ${j.regiao_nome}</small></span>
          <span class="preco-frete ${o.gratis ? "gratis" : ""}">${o.gratis ? "Grátis" : fmt(o.preco_cents)}</span>
        </label>`).join("");
      $$("input[name=frete_metodo]", caixaFrete).forEach((r) => r.addEventListener("change", atualizarTotal));
      atualizarTotal();
    } catch (e) { caixaFrete.innerHTML = '<p class="msg-erro">Não consegui calcular o frete. Tente de novo.</p>'; }
  }

  async function buscarCep() {
    const d = (cep.value || "").replace(/\D/g, "");
    if (d.length !== 8) return;
    cep.value = d.slice(0, 5) + "-" + d.slice(5);
    try {
      const r = await fetch("https://viacep.com.br/ws/" + d + "/json/");
      const j = await r.json();
      if (!j.erro) {
        const set = (id, v) => { const el = $(id); if (el && v && !el.value) el.value = v; };
        set("#logradouro", j.logradouro); set("#bairro", j.bairro); set("#cidade", j.localidade);
        if ($("#uf") && j.uf) $("#uf").value = j.uf;
        if (j.logradouro && $("#numero")) $("#numero").focus();
      }
    } catch (e) { /* preenche na mão */ }
    cotarFrete();
  }
  cep.addEventListener("blur", buscarCep);
  cep.addEventListener("input", () => { if (cep.value.replace(/\D/g, "").length === 8) buscarCep(); });
  if (cep.value.replace(/\D/g, "").length === 8) cotarFrete();

  const cupom = $("#cupom");
  const btnCupom = $("#aplicar-cupom");
  async function aplicarCupom() {
    const codigo = (cupom.value || "").trim();
    const msg = $("#cupom-msg");
    if (!codigo) { desconto = 0; form.dataset.tipoCupom = ""; msg.textContent = ""; atualizarTotal(); return; }
    const r = await fetch("/api/cupom?codigo=" + encodeURIComponent(codigo), { headers: { Accept: "application/json" } });
    const j = await r.json();
    if (!j.ok) { desconto = 0; form.dataset.tipoCupom = ""; msg.textContent = j.erro; msg.className = "msg-erro"; }
    else { desconto = j.desconto_cents; form.dataset.tipoCupom = j.tipo; msg.textContent = j.tipo === "frete" ? "Cupom aplicado: frete grátis." : "Cupom aplicado."; msg.className = "ajuda"; }
    atualizarTotal();
  }
  if (btnCupom) btnCupom.addEventListener("click", aplicarCupom);
  if (cupom && cupom.value) aplicarCupom();

  // máscaras leves
  const mask = (el, f) => el && el.addEventListener("input", () => { el.value = f(el.value); });
  mask($("#cpf"), (v) => v.replace(/\D/g, "").slice(0, 11).replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2"));
  mask($("#telefone"), (v) => { const d = v.replace(/\D/g, "").slice(0, 11); return d.length > 6 ? `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}` : d.length > 2 ? `(${d.slice(0, 2)}) ${d.slice(2)}` : d; });
})();
