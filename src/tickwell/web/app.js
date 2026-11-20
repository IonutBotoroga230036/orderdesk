"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { emails: [], selected: null, current: null, products: [], customers: [], busy: false };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("on"), 2800); }
const productLabel = (code) => { const p = S.products.find((x) => x.code === code); return p ? `${p.label} (${p.code})` : code; };
const stockOf = (code) => (S.products.find((x) => x.code === code) || {}).stock;

async function loadAll() {
  [S.products, S.customers, S.emails] = await Promise.all([api("/api/products"), api("/api/customers"), api("/api/emails")]);
  await loadStats();
  renderList();
  if (!S.selected && S.emails.length) select(S.emails[0].id);
}
async function loadStats() {
  const s = await api("/api/stats");
  $("#stats").innerHTML = `<span><b>${s.open}</b> open</span><span><b>${s.approved}</b> approved</span><span>avg review <b>${s.avg_review_seconds ? fmtSecs(s.avg_review_seconds) : "n/a"}</b></span>`;
}
const fmtSecs = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function renderList() {
  $("#list").innerHTML = S.emails.map((e) => `<li><button class="mail${e.id === S.selected ? " sel" : ""}" data-id="${e.id}">
    <strong>${esc(e.customer_name || e.sender)}</strong><span>${esc(e.subject)}</span>
    <span class="pill p-${e.status}">${e.status}</span></button></li>`).join("") || `<li class="pad muted">No emails yet. Use "Fetch new mail".</li>`;
}

async function select(id) {
  S.selected = id;
  renderList();
  S.current = await api(`/api/emails/${id}`);
  render();
}

/* highlight the words each line came from */
function highlight(text, draft) {
  if (!draft) return esc(text);
  const marks = [];
  const add = (phrase, idx, kind, status) => {
    if (!phrase) return;
    const ex = marks.find((m) => m.phrase === phrase && m.kind === kind);
    if (ex) { if (idx != null) { ex.lines.push(idx); ex.statuses.push(status); } return; }
    const start = text.indexOf(phrase);
    if (start < 0) return;
    const end = start + phrase.length;
    if (marks.some((m) => start < m.end && end > m.start)) return;
    marks.push({ phrase, start, end, kind, lines: idx != null ? [idx] : [], statuses: [status] });
  };
  draft.lines.forEach((l, i) => add(l.source_text, l.removed ? null : i, l.removed ? "rm" : "line", lineStatus(l)));
  add(draft.delivery_text, null, "dl");
  marks.sort((a, b) => a.start - b.start);
  let html = "", pos = 0;
  for (const m of marks) {
    html += esc(text.slice(pos, m.start));
    let cls = "hl-" + m.kind, attrs = "", sup = "";
    if (m.kind === "line") {
      cls = "hl-" + (m.statuses.includes("unknown") ? "unknown" : m.statuses.includes("check") ? "check" : "ok");
      attrs = ` data-lines="${m.lines.join(",")}"`;
      sup = `<sup>${m.lines.map((i) => i + 1).join(",")}</sup>`;
    }
    html += `<mark class="${cls}"${attrs}>${esc(text.slice(m.start, m.end))}${sup}</mark>`;
    pos = m.end;
  }
  return html + esc(text.slice(pos));
}
const lineStatus = (l) => (l.needs_review ? (l.product_code ? "check" : "unknown") : "ok");

function render() {
  const e = S.current, d = e.draft;
  $("#email").innerHTML = `<div class="meta">${esc(e.sender)}, ${new Date(e.received_at).toLocaleString()}</div>
    <h2>${esc(e.subject)}</h2><div class="body">${highlight(e.body_text, d)}</div>
    ${e.attachments.map((a) => `<div class="att"><h3>${esc(a.filename)}</h3><pre>${highlight(a.text || "(no readable text)", d)}</pre></div>`).join("")}`;
  if (!d) {
    $("#draft").innerHTML = `<div class="pad"><h3>No draft yet</h3>${e.error ? `<p class="muted">${esc(e.error)}</p>` : ""}
      <p class="muted">Reads the email and attachments, recognises the customer, matches items to the catalog and checks stock.</p>
      <button class="btn" data-act="draft">Draft order</button></div>`;
    return;
  }
  if (d.approved_at) {
    $("#draft").innerHTML = `<div class="pad"><h3>Approved as ${esc(d.erp_reference)}</h3>
      <p class="muted">Reviewed in ${d.review_seconds ? fmtSecs(d.review_seconds) : "n/a"}.</p>
      ${d.lines.filter((l) => !l.removed && l.quantity > 0).map((l) => `<div>${l.quantity} × ${esc(productLabel(l.product_code))}</div>`).join("")}</div>`;
    return;
  }
  const custOpts = S.customers.map((c) => `<option value="${c.id}"${c.id === d.customer_id ? " selected" : ""}>${esc(c.name)} (${c.id})</option>`).join("");
  const lines = d.lines.map((l, i) => l.removed ? removedLine(l) : lineRow(l, i)).join("");
  const prodOpts = S.products.map((p) => `<option value="${p.code}">${esc(p.label)} (${p.code})</option>`).join("");
  $("#draft").innerHTML = `<div class="ph">
      <label class="fld"><span>Customer</span><select data-act="customer">${d.customer_id ? "" : `<option value="">Choose a customer</option>`}${custOpts}</select></label>
      <div class="fld"><span>Delivery</span><strong>${esc(d.delivery_date || "Not stated")}</strong>${d.delivery_text ? `<small class="muted">from “${esc(d.delivery_text)}”</small>` : ""}</div>
    </div>
    ${lines || `<div class="pad muted">No order lines found. Add them below.</div>`}
    <div class="add"><select id="add-code" aria-label="Product to add">${prodOpts}</select><input id="add-qty" type="number" min="1" value="1" aria-label="Quantity to add"><button class="ghost" data-act="add">Add line</button></div>
    <div class="pf"><span class="issues">${d.blocking_issues.length ? esc(d.blocking_issues.join(" ")) : "Everything checked"}</span>
      <span><button class="ghost" data-act="redraft">Redraft</button> <button class="btn" data-act="approve"${d.blocking_issues.length ? " disabled" : ""}>Approve and send to ERP</button></span></div>`;
}

function lineRow(l, i) {
  const st = lineStatus(l);
  const top = [...new Set([...(l.product_code ? [l.product_code] : []), ...l.alternatives])];
  const opts = (l.product_code ? "" : `<option value="" selected>Choose a product</option>`) +
    (top.length ? `<optgroup label="Suggested">${top.map((c) => `<option value="${c}"${c === l.product_code ? " selected" : ""}>${esc(productLabel(c))}</option>`).join("")}</optgroup>` : "") +
    `<optgroup label="All products">${S.products.filter((p) => !top.includes(p.code)).map((p) => `<option value="${p.code}">${esc(p.label)} (${p.code})</option>`).join("")}</optgroup>`;
  const stock = l.product_code != null ? stockOf(l.product_code) : null;
  let act;
  if (!l.needs_review) act = `<span class="chip">${l.resolved && l.status !== "ok" ? "Checked" : "Matched"}</span>`;
  else if (l.product_code) act = `<button class="confirm" data-act="confirm" data-line="${l.id}">Looks right</button>`;
  else act = `<span class="chip bad">Pick a product</span>`;
  return `<div class="line st-${st}" data-i="${i}">
    <div class="n">${i + 1}</div>
    <div>${l.source_text ? `<div class="said">Customer wrote “${esc(l.source_text)}”</div>` : ""}
      <select data-act="product" data-line="${l.id}" aria-label="Product for line ${i + 1}">${opts}</select>
      ${l.reason ? `<p class="why">${esc(l.reason)}</p>` : ""}
      ${stock != null ? `<p class="why">${stock} in stock</p>` : ""}</div>
    <div><input type="number" min="0" value="${l.quantity}" data-act="qty" data-line="${l.id}" aria-label="Quantity for line ${i + 1}"></div>
    <div class="act">${act}</div></div>`;
}
const removedLine = (l) => `<div class="line removed"><div class="n">×</div><div><div class="said">Customer wrote “${esc(l.source_text)}”</div><s>${esc(productLabel(l.product_code))}, ${l.quantity}</s>${l.reason ? `<p class="why">${esc(l.reason)}</p>` : ""}</div><div></div><div class="act"><span class="chip">Removed</span></div></div>`;

async function run(fn, okMsg) {
  if (S.busy) return;
  S.busy = true;
  try { const r = await fn(); if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg); return r; }
  catch (err) { toast(err.message); }
  finally { S.busy = false; }
}
async function refreshCurrent(draft) {
  if (draft) S.current.draft = draft;
  else S.current = await api(`/api/emails/${S.selected}`);
  render();
}

/* events */
$("#list").addEventListener("click", (ev) => { const b = ev.target.closest(".mail"); if (b) select(+b.dataset.id); });
$("#fetch").addEventListener("click", () => run(async () => {
  const r = await api("/api/ingest", { method: "POST" });
  S.emails = await api("/api/emails"); renderList(); await loadStats(); return r;
}, (r) => `${r.new_emails} new email(s)`));

$("#draft").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-act]"); if (!b) return;
  const d = S.current.draft, act = b.dataset.act;
  if (act === "draft" || act === "redraft") run(async () => {
    b.disabled = true; b.textContent = "Drafting…";
    await api(`/api/emails/${S.selected}/draft`, { method: "POST" });
    S.emails = await api("/api/emails"); renderList(); await refreshCurrent();
  }, "Draft ready");
  if (act === "confirm") run(async () => refreshCurrent(await api(`/api/drafts/${d.id}/lines/${b.dataset.line}`, { method: "PATCH", body: JSON.stringify({ resolved: true }) })));
  if (act === "add") run(async () => refreshCurrent(await api(`/api/drafts/${d.id}/lines`, { method: "POST", body: JSON.stringify({ product_code: $("#add-code").value, quantity: +$("#add-qty").value }) })));
  if (act === "approve") run(async () => {
    const r = await api(`/api/drafts/${d.id}/approve`, { method: "POST" });
    [S.emails, S.products] = await Promise.all([api("/api/emails"), api("/api/products")]);
    renderList(); await loadStats(); await refreshCurrent(r); return r;
  }, (r) => `Sent to ERP as ${r.erp_reference}`);
});
$("#draft").addEventListener("change", (ev) => {
  const t = ev.target, d = S.current && S.current.draft; if (!d) return;
  if (t.dataset.act === "product") run(async () => refreshCurrent(await api(`/api/drafts/${d.id}/lines/${t.dataset.line}`, { method: "PATCH", body: JSON.stringify(t.value ? { product_code: t.value } : { clear_product: true }) })));
  if (t.dataset.act === "qty") run(async () => refreshCurrent(await api(`/api/drafts/${d.id}/lines/${t.dataset.line}`, { method: "PATCH", body: JSON.stringify({ quantity: Math.max(0, Math.round(+t.value || 0)) }) })));
  if (t.dataset.act === "customer") run(async () => refreshCurrent(await api(`/api/drafts/${d.id}`, { method: "PATCH", body: JSON.stringify({ customer_id: t.value }) })));
});

/* hover a line to see where it came from, and the other way round */
function light(target) {
  document.querySelectorAll(".lit").forEach((x) => x.classList.remove("lit"));
  const row = target.closest && target.closest(".line[data-i]");
  const mk = target.closest && target.closest("mark[data-lines]");
  if (row) {
    row.classList.add("lit");
    document.querySelectorAll("mark[data-lines]").forEach((m) => { if (m.dataset.lines.split(",").includes(row.dataset.i)) m.classList.add("lit"); });
  } else if (mk) {
    mk.classList.add("lit");
    mk.dataset.lines.split(",").forEach((i) => { const r = document.querySelector(`.line[data-i="${i}"]`); if (r) r.classList.add("lit"); });
  }
}
document.addEventListener("mouseover", (ev) => light(ev.target));
document.addEventListener("focusin", (ev) => light(ev.target));

loadAll().catch((err) => toast(err.message));
