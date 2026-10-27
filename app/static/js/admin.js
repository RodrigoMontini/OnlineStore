/* Painel: confirmações, separação por toque, copiar, menu "mais", assistente. */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const csrf = (document.querySelector('meta[name="csrf"]') || {}).content || "";

  // Confirmação em ações destrutivas
  $$("form[data-confirmar]").forEach((f) => f.addEventListener("submit", (e) => {
    if (!confirm(f.dataset.confirmar)) e.preventDefault();
  }));

  // Menu "mais" no celular
  const btnMais = $("#btn-mais");
  const menuMais = $("#menu-mais");
  if (btnMais && menuMais) {
    btnMais.addEventListener("click", (e) => { e.preventDefault(); menuMais.classList.toggle("aberto"); });
    menuMais.addEventListener("click", (e) => { if (e.target === menuMais) menuMais.classList.remove("aberto"); });
  }

  // Copiar
  $$("[data-copiar]").forEach((b) => b.addEventListener("click", async () => {
    const alvo = $(b.dataset.copiar);
    const texto = alvo ? (alvo.value || alvo.textContent) : b.dataset.texto;
    try { await navigator.clipboard.writeText(texto.trim()); } catch (e) { if (alvo && alvo.select) { alvo.select(); document.execCommand("copy"); } }
    const antes = b.textContent; b.textContent = "Copiado"; setTimeout(() => (b.textContent = antes), 1800);
  }));

  // Separação: marcar item por toque
  $$(".separacao-item input[type=checkbox]").forEach((cb) => cb.addEventListener("change", async () => {
    const item = cb.closest(".separacao-item");
    item.classList.toggle("ok", cb.checked);
    const r = await fetch(`/admin/pedidos/${cb.dataset.pedido}/separar-item`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ item_id: parseInt(cb.value, 10), separado: cb.checked }),
    });
    const j = await r.json().catch(() => ({}));
    const btn = $("#btn-concluir-separacao");
    if (btn) btn.disabled = !j.todos;
  }));

  // Marcar mensagem como enviada ao abrir o WhatsApp
  $$("[data-enviada]").forEach((a) => a.addEventListener("click", () => {
    fetch(`/admin/mensagens/${a.dataset.enviada}/enviada`, { method: "POST", headers: { Accept: "application/json", "X-CSRF-Token": csrf } });
    const linha = a.closest("[data-linha]"); if (linha) linha.style.opacity = ".5";
  }));

  // Assistente: descrição de produto
  const btnDescrever = $("#btn-descrever");
  if (btnDescrever) btnDescrever.addEventListener("click", async () => {
    btnDescrever.disabled = true; btnDescrever.textContent = "Escrevendo…";
    const cat = $("#categoria_id"); const catNome = cat && cat.selectedIndex >= 0 ? cat.options[cat.selectedIndex].text : "";
    const r = await fetch(btnDescrever.dataset.url, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ nome: $("#nome").value, categoria: catNome, notas: $("#descricao").value }),
    });
    const j = await r.json();
    if (j.ok) { if (j.resumo) $("#resumo").value = j.resumo; if (j.descricao) $("#descricao").value = j.descricao; }
    else alert(j.erro || "Não deu certo.");
    btnDescrever.disabled = false; btnDescrever.textContent = "Escrever com o assistente";
  });

  // Assistente: resposta de ticket
  const btnSugerir = $("#btn-sugerir");
  if (btnSugerir) btnSugerir.addEventListener("click", async () => {
    btnSugerir.disabled = true; btnSugerir.textContent = "Pensando…";
    const r = await fetch(btnSugerir.dataset.url, { method: "POST", headers: { "X-CSRF-Token": csrf } });
    const j = await r.json();
    if (j.ok) $("#resposta").value = j.texto; else alert(j.erro || "Não deu certo.");
    btnSugerir.disabled = false; btnSugerir.textContent = "Sugerir resposta";
  });

  // Link do WhatsApp a partir do texto digitado
  const resposta = $("#resposta");
  const linkWa = $("#link-wa-resposta");
  if (resposta && linkWa) {
    const base = linkWa.dataset.base;
    const atualizar = () => { linkWa.href = base + encodeURIComponent(resposta.value); };
    resposta.addEventListener("input", atualizar); atualizar();
  }

  // Impressão automática
  if (document.body.dataset.imprimir === "1") setTimeout(() => window.print(), 300);
})();
