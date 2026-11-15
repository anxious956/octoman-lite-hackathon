// OctoMan Lite dashboard. One ES module, no framework, no build step.
// API data is only ever written with textContent / DOM APIs.

import * as D from "./derive.js";

// ── config ──────────────────────────────────────────────────────────
const POLL_MS = 2000;      // poll every 2 s ...
const BURST_MS = 20000;    // ... for 20 s after an action, then stop
const STALE_MS = 30000;    // refresh once when the tab comes back after this long
const BUSY_MS = 1000;      // order buttons rest for 1 s after a click
const MAX_ORDERS_SHOWN = 25;
const RESTOCK_REST_MS = 5000; // restock button rests for 5 s after a reset

const cfg = window.OCTOMAN_LITE_CONFIG || {};
const params = new URLSearchParams(location.search);
const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
// ?api= only on a local test server or when there is no deployed config, so nobody can
// craft a link that makes the real dashboard show data from another server.
const override = (isLocal || !cfg.apiUrl) ? params.get("api") : null;
const API = (override || cfg.apiUrl || "").replace(/\/+$/, "");
const EXEC = cfg.stateMachineArn && cfg.region ? { arn: cfg.stateMachineArn, region: cfg.region } : null;

// ── state ───────────────────────────────────────────────────────────
const state = {
  products: [], orders: [], alerts: [],
  focusedOrderId: params.get("focus") || null,
  expandedOrderId: params.get("focus") || null,
  lastSku: null,
  qtyBySku: {},
  filter: "all",
  lastUpdated: 0,
  loaded: false,
  error: null,
  busyUntil: 0,
  pending: new Map(), // order_id -> accepted by the API, not yet in GET /orders
  confirmRestock: false,
  resetting: false,
  restockRestUntil: 0,
  tab: "live",
};
const prev = { listed: {}, stock: {}, shelfSku: null, shelfStock: null };

// ── api ─────────────────────────────────────────────────────────────
async function request(path, init = {}) {
  const opts = { ...init };
  if (opts.body) opts.headers = { "content-type": "application/json" }; // never on GET: no preflight
  let resp;
  try {
    resp = await fetch(API + path, opts);
  } catch (e) {
    return { status: 0, body: null };
  }
  let body = null;
  try { body = await resp.json(); } catch (e) { body = null; }
  return { status: resp.status, body };
}

async function getAll() {
  const [p, o, a] = await Promise.all([request("/products"), request("/orders?limit=100"), request("/alerts")]);
  const bad = [p, o, a].find((r) => r.status !== 200);
  if (bad) throw new Error(bad.status === 0 ? "network" : `HTTP ${bad.status}`);
  return { products: p.body.products || [], orders: o.body.orders || [], alerts: a.body.alerts || [] };
}

function postOrder(order) {
  return request("/orders", { method: "POST", body: JSON.stringify(order) });
}

/** One place that turns an HTTP result into words for a shop owner. */
function messageFor(res) {
  if (res.status === 0) return "Can't reach the store data.";
  if (res.status === 429) return "Too many orders, wait a second.";
  if (res.status === 409) return "That order was already received.";
  const errs = res.body && res.body.errors;
  if (errs && errs.length) return errs.join(" ");
  if (res.body && res.body.message) return res.body.message;
  return `Order failed (error ${res.status}).`;
}

// ── tiny DOM helpers ────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

function el(tag, props, children) {
  const node = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "text") node.textContent = String(v);
      else if (k === "class") node.className = v;
      else if (k === "on") for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
      else if (k === "dataset") Object.assign(node.dataset, v);
      else node.setAttribute(k, v === true ? "" : String(v));
    }
  }
  for (const c of children || []) if (c) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";
function icon(name, cls = "icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.appendChild(use);
  return svg;
}

function img(src, cls, size, alt = "") {
  const node = el("img", { src, class: cls, width: size, height: size, alt, decoding: "async" });
  node.addEventListener("error", () => { node.src = "assets/img/logo.png"; }, { once: true });
  return node;
}

function flag(market) {
  return el("img", { src: `assets/img/flags/${market.flag}.svg`, class: "flag", alt: "", width: 20, height: 15 });
}

function setText(node, text) {
  const t = String(text ?? "");
  if (node.textContent !== t) node.textContent = t;
}

function flash(node, cls = "is-updated", delay = 0) {
  setTimeout(() => {
    node.classList.add(cls);
    setTimeout(() => node.classList.remove(cls), 1600);
  }, delay);
}

function productTitle(sku) {
  const p = state.products.find((x) => x.sku === sku);
  return p ? p.title : sku;
}

/** Countable boxes for 10 or fewer, otherwise a bar with a tick at the warning level. */
function unitsVisual(p, maxUnits) {
  const left = D.unitsLeft(p), warn = D.warnBelow(p);
  const status = D.productStatus(p);
  if (left <= 10 && Math.max(left, warn) <= 10) {
    const wrap = el("div", { class: `units is-${status}`, role: "img",
      "aria-label": `${left} left, warning below ${warn}` });
    for (let i = 0; i < Math.max(left, warn); i += 1) {
      wrap.appendChild(el("span", { class: i < left ? "unit" : "unit unit--warn" }));
    }
    return wrap;
  }
  const scale = Math.max(maxUnits, left, warn, 1);
  const meter = el("div", { class: `meter is-${status}`, role: "img",
    "aria-label": `${left} left, warning below ${warn}` });
  const fill = el("span", { class: "meter__fill" });
  fill.style.width = `${(left / scale) * 100}%`;
  const tick = el("span", { class: "meter__tick" });
  tick.style.left = `${(warn / scale) * 100}%`;
  meter.append(fill, tick);
  return meter;
}

function statusChip(p) {
  const s = D.productStatus(p);
  const ic = s === "ok" ? "check" : s === "low" ? "triangle-alert" : "octagon-x";
  return el("span", { class: `chip chip--${s}` }, [icon(ic), D.STATUS_TEXT[s]]);
}

const SYNC_TEXT = { seeded: "Listed", synced: "Updated", origin: "Sold here", error: "Update failed" };

// ── toasts ──────────────────────────────────────────────────────────
function toast(text, kind = "info") {
  const box = $("toasts");
  const ic = kind === "ok" ? "check" : kind === "bad" ? "octagon-x" : "info";
  const node = el("div", { class: `toast toast--${kind}`, role: kind === "bad" ? "alert" : "status" },
    [icon(ic), el("span", { text })]);
  box.appendChild(node);
  while (box.children.length > 3) box.removeChild(box.firstChild);
  setTimeout(() => node.remove(), kind === "bad" ? 7000 : 5000);
}

// ── derived views of state ──────────────────────────────────────────
function focusedOrder() {
  const id = state.focusedOrderId;
  if (id) {
    const o = state.orders.find((x) => x.order_id === id);
    if (o) return o;
    if (state.pending.has(id)) return { ...state.pending.get(id), pending: true };
  }
  return state.orders[0] || null;
}

function inStockCount() {
  return state.products.filter((p) => D.unitsLeft(p) > 0).length;
}

function isBusy() {
  return Date.now() < state.busyUntil;
}

// ── render: header ──────────────────────────────────────────────────
function renderLive(polling) {
  const live = $("live");
  if (state.error) {
    live.dataset.state = "error";
    setText($("live-text"), "Offline");
  } else if (!state.loaded) {
    live.dataset.state = "busy";
    setText($("live-text"), "Connecting…");
  } else {
    live.dataset.state = polling ? "busy" : "ok";
    const t = new Date(state.lastUpdated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    setText($("live-text"), polling ? `Live · refreshing · ${t}` : `Live · updated ${t}`);
  }
}

function renderBanner() {
  const show = Boolean(state.error);
  $("banner").hidden = !show;
  if (show) {
    setText($("banner-text"), state.loaded
      ? "Connection lost, data may be outdated."
      : "Store data can't be reached.");
  }
}

// ── render: shelf picture ───────────────────────────────────────────
const shelfRefs = {};
function buildShelf() {
  const core = $("shelf-core");
  core.textContent = "";
  shelfRefs.img = img("assets/img/logo.png", "shelf__img", 88);
  shelfRefs.title = el("figcaption", { class: "shelf__title" });
  shelfRefs.num = el("span", { class: "shelf__num" });
  shelfRefs.unitsLabel = el("span", { class: "shelf__numlabel" });
  shelfRefs.visual = el("div", { class: "shelf__visual" });
  shelfRefs.meta = el("div", { class: "shelf__meta" });
  core.append(shelfRefs.img, el("div", { class: "shelf__text" }, [
    el("div", { class: "shelf__label", text: "The shared shelf" }),
    shelfRefs.title,
    el("div", { class: "shelf__units" }, [shelfRefs.num, shelfRefs.unitsLabel, shelfRefs.meta]),
    shelfRefs.visual,
  ]));
  shelfRefs.shops = {};
  for (const node of document.querySelectorAll(".shop")) {
    const m = D.MARKET_BY_ID[node.dataset.market];
    const qty = el("div", { class: "shop__qty" });
    const price = el("span", { class: "shop__price" });
    const sync = el("span", { class: "shop__sync" });
    node.textContent = "";
    node.append(
      el("div", { class: "shop__name" }, [flag(m), m.name]),
      el("div", { class: "shop__store", text: m.store }),
      qty, el("div", { class: "shop__label", text: "shown as available" }),
      el("div", { class: "shop__foot" }, [price, sync]));
    shelfRefs.shops[m.id] = { node, qty, price, sync };
  }
}

function renderShelf(maxUnits) {
  const fo = focusedOrder();
  const p = D.focusProduct(state.products, fo, state.lastSku);
  if (!p) return;
  if (!shelfRefs.num) buildShelf();
  const left = D.unitsLeft(p);
  const sameProduct = prev.shelfSku === p.sku;

  shelfRefs.img.src = D.productImage(p.sku);
  shelfRefs.img.alt = p.title;
  setText(shelfRefs.title, p.title);
  shelfRefs.title.title = `${p.title} (${p.sku})`;
  setText(shelfRefs.num, left);
  setText(shelfRefs.unitsLabel, left === 1 ? "unit left" : "units left");
  if (sameProduct && prev.shelfStock !== null && left < prev.shelfStock) {
    shelfRefs.num.classList.remove("is-drop");
    void shelfRefs.num.offsetWidth; // restart the animation
    shelfRefs.num.classList.add("is-drop");
  }
  shelfRefs.visual.replaceChildren(unitsVisual(p, maxUnits),
    el("span", { class: "muted small", text: `Warn below ${D.warnBelow(p)}` }));
  shelfRefs.meta.replaceChildren(statusChip(p));

  D.MARKETS.forEach((m, i) => {
    const r = shelfRefs.shops[m.id];
    const l = (p.listings || {})[m.id];
    const isOrigin = fo && fo.status === "COMPLETED" && fo.sku === p.sku && fo.marketplace === m.id;
    r.node.classList.toggle("is-origin", Boolean(isOrigin));
    if (!l) {
      setText(r.qty, "–"); setText(r.price, "not listed"); setText(r.sync, "");
      return;
    }
    const prevQty = prev.listed[`${p.sku}|${m.id}`];
    setText(r.qty, l.listed_qty);
    setText(r.price, D.formatMoney(l.price, l.currency));
    setText(r.sync, ` · ${SYNC_TEXT[l.sync_status] || l.sync_status || ""}`);
    // The four shops light up one after another, in reading order.
    if (sameProduct && prevQty !== undefined && prevQty !== l.listed_qty) flash(r.node, "is-updated", i * 120);
  });
  prev.shelfSku = p.sku;
  prev.shelfStock = left;
}

function renderSummary() {
  const s = D.summary(state.orders, state.alerts);
  const part = (n, label, key) => el("span", { class: key ? "is-key" : null }, [el("b", { text: n }), ` ${label}`]);
  const sep = () => el("span", { class: "summary__sep", "aria-hidden": "true", text: "·" });
  $("summary").replaceChildren(
    part(s.orders, s.orders === 1 ? "order" : "orders"), sep(),
    part(s.sold, "sold"), sep(),
    part(s.blocked, s.blocked === 1 ? "oversell blocked" : "oversells blocked", true), sep(),
    part(s.lowWarnings, s.lowWarnings === 1 ? "low-stock warning" : "low-stock warnings"), sep(),
    part(D.formatMoney(s.salesUsd, "USD"), "in sales"));
}

// ── render: flow strip ──────────────────────────────────────────────
const flowRefs = [];
function buildFlow() {
  const ol = $("flow-steps");
  ol.textContent = "";
  for (const step of D.FLOW_STEPS) {
    const node = el("span", { class: "step__node" }, [icon(step.icon)]);
    const note = el("span", { class: "step__note" });
    const li = el("li", { class: "step", dataset: { state: "waiting" } }, [
      node, el("span", { class: "step__name", text: step.name }),
      el("span", { class: "step__cap", text: step.caption }), note]);
    ol.appendChild(li);
    flowRefs.push({ li, node, note, step });
  }
}

function renderFlow() {
  if (!flowRefs.length) buildFlow();
  const fo = focusedOrder();
  const { states, notes } = D.flowStates(fo, state.alerts);
  flowRefs.forEach((r, i) => {
    if (r.li.dataset.state !== states[i]) {
      r.li.dataset.state = states[i];
      r.node.replaceChildren(icon(states[i] === "blocked" ? "octagon-x" : r.step.icon));
    }
    setText(r.note, notes[i]);
    r.li.setAttribute("aria-label", `${r.step.name}: ${states[i]}${notes[i] ? `. ${notes[i]}` : ""}`);
  });
  const head = $("flow-order");
  if (!fo) {
    head.replaceChildren("Press Try the demo to start.");
    return;
  }
  const m = D.MARKET_BY_ID[fo.marketplace];
  const st = fo.pending ? { text: "Processing" } : D.orderStatus(fo);
  head.replaceChildren(
    m ? flag(m) : "",
    el("span", { text: `${m ? m.name : fo.marketplace} · ${fo.quantity} × ${productTitle(fo.sku)} · ${st.text} · ${D.timeAgo(fo.created_at)}` }));
}

// ── render: try it ──────────────────────────────────────────────────
function renderTryit() {
  // Data written by an older version (e.g. eBay store keys) has no listing for any
  // current store: lead with Restock, which rewrites every product in one click.
  const outdated = state.loaded && state.products.length > 0 && D.hasNoKnownListings(state.products);
  const soldOut = !outdated && state.loaded && state.products.length > 0 && inStockCount() === 0;
  const needsRestock = outdated || soldOut;
  const picks = {
    sell: D.pickSellOne(state.products), low: D.pickLowStock(state.products),
    race: D.pickRace(state.products, () => 0), oversell: D.pickOversell(state.products),
  };
  for (const b of document.querySelectorAll(".story")) {
    b.disabled = !state.loaded || isBusy() || !picks[b.dataset.scenario];
  }
  // Restock: a quiet secondary action, the primary one when nothing can be sold.
  $("demo").classList.toggle("is-soldout", needsRestock);
  setText($("demo-open-text"), outdated ? "Restock the demo to start"
    : soldOut ? "Sold out: restock the demo" : "Try the demo");
  const restock = $("restock");
  restock.classList.toggle("btn--brand", needsRestock);
  restock.disabled = !API || state.resetting || Date.now() < state.restockRestUntil;
  restock.setAttribute("aria-expanded", String(state.confirmRestock));
  $("restock-confirm").hidden = !state.confirmRestock;
}

// ── restock the demo (POST /demo/reset) ─────────────────────────────
function askRestock() {
  state.confirmRestock = true;
  renderTryit();
  $("restock-yes").focus();
}

function cancelRestock() {
  state.confirmRestock = false;
  renderTryit();
  $("restock").focus();
}

async function restock() {
  state.confirmRestock = false;
  state.resetting = true;
  renderTryit();
  // No body and no custom headers: a simple request, no CORS preflight.
  let res = await request("/demo/reset", { method: "POST" });
  if (res.status === 200 && res.body && res.body.more) res = await request("/demo/reset", { method: "POST" });
  state.resetting = false;
  state.restockRestUntil = Date.now() + RESTOCK_REST_MS;
  setTimeout(renderTryit, RESTOCK_REST_MS + 30);
  if (res.status === 200) {
    toast("Demo restocked.", "ok");
    closeDemo(false);
    state.focusedOrderId = null;
    state.expandedOrderId = null;
    state.lastSku = null;
    state.pending.clear();
    await refresh();
  } else {
    toast(res.status === 429 ? "Just restocked, try again shortly." : messageFor(res), "bad");
    renderTryit();
  }
}

// ── render: inventory (keyed, updated in place) ─────────────────────
const rowRefs = new Map();

function buildRow(p) {
  const refs = {};
  refs.img = img(D.productImage(p.sku), "product__img", 64);
  refs.title = el("div", { class: "product__title" });
  refs.sku = el("div", { class: "product__sku" });
  refs.num = el("span", { class: "product__num" });
  refs.numLabel = el("span", { class: "product__numlabel" });
  refs.visual = el("div");
  refs.chip = el("span");
  // The four stores: each shows what that Amazon store displays, and is the button that
  // makes a customer there buy. Same width, same order as the shelf picture above.
  refs.markets = {};
  const marketGrid = el("div", { class: "markets" });
  for (const m of D.MARKETS) {
    const qty = el("span", { class: "market__qty" });
    const price = el("span", { class: "market__price" });
    const cta = el("span", { class: "market__cta", text: "Sell" });
    const cell = el("button", { type: "button", class: "market", on: { click: () => sellFromRow(p.sku, m.id) } }, [
      el("span", { class: "market__head" }, [flag(m), m.code]), qty, price, cta]);
    marketGrid.appendChild(cell);
    refs.markets[m.id] = { cell, qty, price, market: m };
  }

  refs.input = el("input", { type: "number", min: 1, max: D.MAX_QTY, inputmode: "numeric",
    "aria-label": `How many of ${p.title} the customer buys` });
  refs.input.value = String(state.qtyBySku[p.sku] || 1);
  refs.input.addEventListener("input", () => { state.qtyBySku[p.sku] = D.clampQty(refs.input.value); });
  refs.input.addEventListener("change", () => { refs.input.value = String(D.clampQty(refs.input.value)); });
  const step = (d) => () => {
    state.qtyBySku[p.sku] = D.clampQty((state.qtyBySku[p.sku] || 1) + d);
    refs.input.value = String(state.qtyBySku[p.sku]);
    renderRowButtons(p.sku);
  };
  const stepper = el("div", { class: "stepper" }, [
    el("button", { type: "button", "aria-label": "One fewer", on: { click: step(-1) } }, [icon("minus")]),
    refs.input,
    el("button", { type: "button", "aria-label": "One more", on: { click: step(1) } }, [icon("plus")]),
  ]);

  refs.race = el("button", { type: "button", class: "race", on: { click: () => raceFromRow(p.sku) } });

  refs.li = el("li", { class: "product", dataset: { sku: p.sku } }, [
    refs.img,
    el("div", { class: "product__main" }, [
      el("div", { class: "product__top" }, [
        el("div", { class: "product__name" }, [refs.title, refs.sku]),
        el("div", { class: "product__units" }, [refs.num, refs.numLabel, refs.chip]),
      ]),
      refs.visual,
    ]),
    marketGrid,
    el("div", { class: "controls" }, [
      el("span", { class: "controls__label", text: "Units per customer" }), stepper, refs.race]),
  ]);
  rowRefs.set(p.sku, refs);
  return refs;
}

function renderRowButtons(sku) {
  const refs = rowRefs.get(sku);
  const p = state.products.find((x) => x.sku === sku);
  if (!refs || !p) return;
  const qty = state.qtyBySku[sku] || 1;
  const busy = isBusy();
  for (const m of D.MARKETS) {
    const r = refs.markets[m.id];
    const l = (p.listings || {})[m.id];
    r.cell.disabled = busy || !l;
    setText(r.cell.querySelector(".market__cta"), `Sell ${qty}`);
    r.cell.setAttribute("aria-label", l
      ? `${m.name} shows ${l.listed_qty} available at ${D.formatMoney(l.price, l.currency)}. A customer there buys ${qty}.`
      : `${p.title} is not listed in ${m.name}`);
  }
  const left = D.unitsLeft(p);
  refs.race.hidden = left === 0;
  refs.race.disabled = busy;
  refs.race.classList.toggle("is-emphasised", left === 1);
  setText(refs.race, left === 1 ? "Race for the last one" : `Race for all ${left}`);
  refs.race.setAttribute("aria-label",
    `Two customers in two different stores try to buy all ${left} of ${p.title} at the same moment`);
}

function renderProducts(maxUnits) {
  const list = $("products");
  if (!state.loaded) return;
  list.removeAttribute("aria-busy");
  for (const s of list.querySelectorAll(".skeleton")) s.remove();

  const visible = new Set(D.filterProducts(state.products, state.filter).map((p) => p.sku));
  const focusSku = (focusedOrder() || {}).sku;
  // In-stock products first (API order within each group), so a visitor never lands
  // on a wall of sold-out rows. Rows are moved, never rebuilt.
  for (const p of D.inStockFirst(state.products)) {
    const refs = rowRefs.get(p.sku) || buildRow(p);
    if (refs.li.parentNode !== list || list.lastElementChild !== refs.li) list.appendChild(refs.li);
    refs.li.hidden = !visible.has(p.sku);
    refs.li.classList.toggle("is-focused", p.sku === focusSku);
    const left = D.unitsLeft(p);
    setText(refs.title, p.title);
    setText(refs.sku, p.sku);
    setText(refs.num, left);
    setText(refs.numLabel, "left");
    if (prev.stock[p.sku] !== undefined && prev.stock[p.sku] !== left) flash(refs.num, "is-drop");
    refs.visual.replaceChildren(unitsVisual(p, maxUnits));
    refs.chip.replaceChildren(statusChip(p));
    D.MARKETS.forEach((m, i) => {
      const r = refs.markets[m.id];
      const l = (p.listings || {})[m.id];
      setText(r.qty, l ? l.listed_qty : "–");
      setText(r.price, l ? D.formatMoney(l.price, l.currency) : "not listed");
      r.cell.title = l ? `${m.name} · ${SYNC_TEXT[l.sync_status] || l.sync_status}` : `${m.name}: not listed`;
      const k = `${p.sku}|${m.id}`;
      if (l && prev.listed[k] !== undefined && prev.listed[k] !== l.listed_qty) flash(r.cell, "is-updated", i * 120);
    });
    // Never overwrite what the visitor is typing.
    if (document.activeElement !== refs.input) refs.input.value = String(state.qtyBySku[p.sku] || 1);
    renderRowButtons(p.sku);
  }
  for (const [sku, refs] of rowRefs) {
    if (!state.products.some((p) => p.sku === sku)) { refs.li.remove(); rowRefs.delete(sku); }
  }
  const empty = $("products-empty");
  if (!state.products.length) {
    empty.hidden = false;
    setText(empty, "No products yet.");
  } else if (!visible.size) {
    empty.hidden = false;
    setText(empty, state.filter === "low" ? "None running low." : "Nothing sold out.");
  } else {
    empty.hidden = true;
  }
}

// ── render: orders (keyed) ──────────────────────────────────────────
const orderRefs = new Map();

function orderRows() {
  const known = new Set(state.orders.map((o) => o.order_id));
  const pending = [...state.pending.values()].filter((o) => !known.has(o.order_id))
    .map((o) => ({ ...o, pending: true }));
  return [...pending.reverse(), ...state.orders].slice(0, MAX_ORDERS_SHOWN);
}

function buildOrder(o) {
  const refs = {};
  refs.img = img(D.productImage(o.sku), "order__img", 40);
  refs.what = el("div", { class: "order__what" });
  refs.where = el("div", { class: "order__where" });
  refs.total = el("span", { class: "order__total" });
  refs.usd = el("span", { class: "order__usd" });
  refs.chip = el("span");
  refs.why = el("div", { class: "order__why" });
  refs.details = el("dl", { class: "order__details", id: `od-${o.order_id}` });
  refs.btn = el("button", { type: "button", class: "order__btn", "aria-controls": `od-${o.order_id}`,
    on: { click: () => focusOrder(o.order_id, true) } }, [
    refs.img,
    el("div", null, [refs.what, refs.where]),
    el("div", { class: "order__money" }, [refs.total, refs.usd, refs.chip]),
    refs.why,
  ]);
  refs.li = el("li", { class: "order" }, [refs.btn, refs.details]);
  orderRefs.set(o.order_id, refs);
  return refs;
}

function detailRows(o) {
  const rows = [["Order number", o.order_id], ["Received", new Date(o.created_at).toLocaleString()]];
  if (o.status === "COMPLETED") {
    const s = o.sync_summary || {};
    rows.push(["Shelf after", `${o.stock_after} left`]);
    rows.push(["Stores", `${s.synced ?? 0} updated, ${s.skipped ?? 0} already knew, ${s.errored ?? 0} failed`]);
    const note = D.fxNote(o);
    if (note) rows.push(["Price in dollars", `${D.formatMoney(o.base_total, o.base_currency)}, ${note}`]);
    if (o.receipt_key) rows.push(["Receipt", o.receipt_key]);
  }
  return rows;
}

function renderOrderDetails(refs, o, open) {
  refs.details.hidden = !open;
  refs.btn.setAttribute("aria-expanded", open ? "true" : "false");
  if (!open) return;
  const kids = [];
  for (const [k, v] of detailRows(o)) kids.push(el("dt", { text: k }), el("dd", { text: v }));
  if (EXEC && !o.pending) {
    const arn = EXEC.arn.replace(":stateMachine:", ":execution:") + ":" + o.order_id;
    const href = "https://" + EXEC.region + ".console.aws.amazon.com/states/home?region=" + EXEC.region +
      "#/v2/executions/details/" + encodeURIComponent(arn);
    kids.push(el("dt", { text: "Workflow" }),
      el("dd", null, [el("a", { href, target: "_blank", rel: "noopener", text: "Open in the AWS console" })]));
  }
  refs.details.replaceChildren(...kids);
}

function renderOrders() {
  const list = $("orders");
  if (!state.loaded) return;
  list.removeAttribute("aria-busy");
  for (const s of list.querySelectorAll(".skeleton")) s.remove();
  const rows = orderRows();
  const keep = new Set();
  const focusId = (focusedOrder() || {}).order_id;
  rows.forEach((o) => {
    const key = o.order_id;
    keep.add(key);
    const refs = orderRefs.get(key) || buildOrder(o);
    list.appendChild(refs.li); // moves existing nodes into the new order without rebuilding them
    const m = D.MARKET_BY_ID[o.marketplace];
    const st = o.pending ? { key: "processing", text: "Processing" } : D.orderStatus(o);
    refs.li.classList.toggle("is-blocked", st.key === "blocked");
    refs.li.classList.toggle("is-focused", key === focusId);
    setText(refs.what, `${o.quantity} × ${productTitle(o.sku)}`);
    refs.where.replaceChildren(...(m ? [flag(m)] : []), el("span", { text: `${m ? m.name : o.marketplace} · ${D.timeAgo(o.created_at)}` }));
    setText(refs.total, o.total !== undefined ? D.formatMoney(o.total, o.currency) : "");
    const usd = D.usdTotal(o);
    setText(refs.usd, usd !== null && o.currency !== "USD" ? `${D.formatMoney(usd, "USD")} · ECB` : "");
    refs.usd.title = D.fxNote(o);
    const ic = st.key === "sold" ? "check" : st.key === "blocked" ? "octagon-x" : "refresh-cw";
    refs.chip.replaceChildren(el("span", { class: `chip chip--${st.key}` }, [icon(ic), st.key === "blocked" ? "Blocked" : st.text]));
    refs.why.hidden = st.key !== "blocked";
    setText(refs.why, st.key === "blocked" ? D.blockedSentence(o) : "");
    refs.btn.setAttribute("aria-label", `${o.quantity} × ${productTitle(o.sku)} in ${m ? m.name : o.marketplace}: ${st.text}. Show details.`);
    renderOrderDetails(refs, o, state.expandedOrderId === key);
  });
  for (const [key, refs] of orderRefs) {
    if (!keep.has(key)) { refs.li.remove(); orderRefs.delete(key); }
  }
  $("orders-empty").hidden = rows.length > 0;
}

// ── render: alerts ──────────────────────────────────────────────────
function renderAlerts() {
  if (!state.loaded) return;
  const items = state.alerts.map((a) => {
    const m = D.MARKET_BY_ID[a.marketplace];
    const out = a.severity === "OUT_OF_STOCK" || Number(a.stock) <= 0;
    return el("li", { class: "alert" }, [
      img(D.productImage(a.sku), "alert__img", 32),
      el("div", null, [
        el("div", { class: "alert__what", text: a.title || productTitle(a.sku) }),
        el("div", { class: "alert__why",
          text: `${a.stock} left · warn below ${a.threshold} · ${D.timeAgo(a.updated_at)}` }),
      ]),
      el("span", { class: `chip chip--${out ? "out" : "low"}` }, [icon(out ? "octagon-x" : "triangle-alert"), out ? "Sold out" : "Running low"]),
    ]);
  });
  $("alerts").replaceChildren(...items);
  $("alerts-empty").hidden = items.length > 0;
}

// ── render all ──────────────────────────────────────────────────────
function render() {
  const maxUnits = state.products.reduce((mx, p) => Math.max(mx, D.unitsLeft(p)), 0);
  renderLive(pollTimer !== null);
  renderBanner();
  if (state.loaded) {
    renderShelf(maxUnits);
    renderSummary();
    renderFlow();
    renderProducts(maxUnits);
    renderOrders();
    renderAlerts();
  }
  renderTryit();
}

function snapshot() {
  prev.listed = {};
  prev.stock = {};
  for (const p of state.products) {
    prev.stock[p.sku] = D.unitsLeft(p);
    for (const [mp, l] of Object.entries(p.listings || {})) prev.listed[`${p.sku}|${mp}`] = l.listed_qty;
  }
}

// ── data loading and polling ────────────────────────────────────────
let inflight = false;
let pollTimer = null;
let burstUntil = 0;

async function refresh() {
  if (inflight) return;
  inflight = true;
  renderLive(true);
  try {
    const data = await getAll();
    const firstLoad = !state.loaded;
    Object.assign(state, data, { error: null, lastUpdated: Date.now(), loaded: true });
    for (const id of [...state.pending.keys()]) {
      const p = state.pending.get(id);
      if (state.orders.some((o) => o.order_id === id) || Date.now() - Date.parse(p.created_at) > BURST_MS * 2) {
        state.pending.delete(id);
      }
    }
    render();
    snapshot();
    // Open the demo panel once, without taking keyboard focus, when a first-time visitor
    // needs it: a fresh demo (no orders yet) or one that must be restocked first
    // (everything sold out, or products stored by an older version).
    const needsRestock = state.products.length > 0 &&
      (D.hasNoKnownListings(state.products) || inStockCount() === 0);
    if (firstLoad && (!state.orders.length || needsRestock) && $("demo-panel").hidden) openDemo(false);
  } catch (e) {
    state.error = e;
    render();
  } finally {
    inflight = false;
    renderLive(pollTimer !== null);
  }
}

function startBurst() {
  burstUntil = Date.now() + BURST_MS;
  if (pollTimer === null) pollTimer = setInterval(tick, POLL_MS);
}

function tick() {
  if (document.hidden) return; // paused while the tab is in the background
  if (Date.now() > burstUntil) {
    clearInterval(pollTimer);
    pollTimer = null;
    renderLive(false);
    return;
  }
  refresh();
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && state.loaded && Date.now() - state.lastUpdated > STALE_MS) refresh();
});

// ── actions ─────────────────────────────────────────────────────────
/**
 * Send 1 or 2 orders for one product. Requests start in array order, which the
 * caller has already randomised for races. Never more than 2 POSTs per action.
 */
async function placeOrders(product, orders) {
  if (isBusy() || !orders.length) return;
  const batch = orders.slice(0, 2);
  state.busyUntil = Date.now() + BUSY_MS;
  state.lastSku = product.sku;
  render();
  setTimeout(render, BUSY_MS + 30);

  const results = await Promise.all(batch.map((o) => postOrder({ marketplace: o.marketplace, sku: product.sku, quantity: o.quantity })));
  let focused = false;
  results.forEach((res, i) => {
    const o = batch[i];
    const m = D.MARKET_BY_ID[o.marketplace];
    if (res.status === 202 && res.body && res.body.order_id) {
      state.pending.set(res.body.order_id, {
        order_id: res.body.order_id, sku: product.sku, marketplace: o.marketplace, quantity: o.quantity,
        total: res.body.total, currency: res.body.currency, created_at: new Date().toISOString(),
      });
      if (!focused) { focusOrder(res.body.order_id, false); focused = true; }
    } else {
      toast(`${m.name}: ${messageFor(res)}`, "bad");
    }
  });
  render();
  startBurst();
  refresh();
}

function sellFromRow(sku, marketplace) {
  const p = state.products.find((x) => x.sku === sku);
  if (!p) return;
  showTab("live");
  const qty = state.qtyBySku[sku] || 1;
  const m = D.MARKET_BY_ID[marketplace];
  toast(`${m.name} orders ${qty} × ${p.title}`, "info");
  placeOrders(p, [{ marketplace, quantity: qty }]);
}

function raceFromRow(sku) {
  const p = state.products.find((x) => x.sku === sku);
  if (!p) return;
  showTab("live");
  announceRace(p, D.raceOrders(p));
}

function announceRace(p, orders) {
  const [a, b] = orders.map((o) => D.MARKET_BY_ID[o.marketplace].name);
  const n = orders[0].quantity;
  toast(`${a} and ${b} both want ${n === 1 ? "the last" : `all ${n}`} × ${p.title}`, "info");
  placeOrders(p, orders);
}

// ── tabs ────────────────────────────────────────────────────────────
/**
 * Show one view. Only visibility changes: every panel keeps rendering from the same
 * polled data, so a tab is never stale or empty when it opens.
 */
function showTab(name, { push = true } = {}) {
  const changed = state.tab !== name;
  state.tab = name;
  for (const id of D.TABS) {
    const on = id === name;
    const tab = $(`tab-${id}`);
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    $(`panel-${id}`).hidden = !on;
  }
  if (push && location.hash !== `#${name}`) {
    history.pushState(null, "", `${location.pathname}${location.search}#${name}`);
  }
  if (changed && window.scrollY > 0) window.scrollTo(0, 0);
}

// ── the corner demo panel ───────────────────────────────────────────
function openDemo(focus = true) {
  $("demo-panel").hidden = false;
  $("demo-open").setAttribute("aria-expanded", "true");
  const first = $("demo-panel").querySelector(".story:not(:disabled)") || $("restock");
  if (focus) first.focus();
}

function closeDemo(returnFocus = true) {
  if ($("demo-panel").hidden) return;
  $("demo-panel").hidden = true;
  $("demo-open").setAttribute("aria-expanded", "false");
  state.confirmRestock = false;
  renderTryit();
  if (returnFocus) $("demo-open").focus();
}

function runScenario(name) {
  closeDemo(false); // get out of the way so the visitor watches the shelf and the flow
  showTab("live");

  const ps = state.products;
  if (name === "sell") {
    const pick = D.pickSellOne(ps);
    if (!pick) return;
    toast(`Germany buys 1 × ${pick.product.title}`, "info");
    placeOrders(pick.product, pick.orders);
  } else if (name === "low") {
    const pick = D.pickLowStock(ps);
    if (!pick) return;
    const p = pick.product, q = pick.orders[0].quantity;
    toast(`United States buys ${q} × ${p.title}`, "info");
    placeOrders(p, pick.orders);
  } else if (name === "race") {
    const pick = D.pickRace(ps);
    if (!pick) return;
    announceRace(pick.product, pick.orders);
  } else if (name === "oversell") {
    const pick = D.pickOversell(ps);
    if (!pick) return;
    const p = pick.product;
    toast(`United Kingdom asks for ${pick.orders[0].quantity} × ${p.title}`, "info");
    placeOrders(p, pick.orders);
  }
}

function focusOrder(id, toggleDetails) {
  state.focusedOrderId = id;
  if (toggleDetails) state.expandedOrderId = state.expandedOrderId === id ? null : id;
  render();
}

function setFilter(f) {
  state.filter = f;
  for (const b of document.querySelectorAll(".segmented__btn")) b.setAttribute("aria-pressed", String(b.dataset.filter === f));
  render();
}

// ── theme ───────────────────────────────────────────────────────────
function effectiveTheme() {
  const t = document.documentElement.getAttribute("data-theme");
  if (t) return t;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function syncThemeButton() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  $("theme").setAttribute("aria-label", `Switch to ${next} theme`);
}

function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("octoman-lite-theme", next); } catch (e) { /* private mode: not remembered */ }
  syncThemeButton();
}

// ── start ───────────────────────────────────────────────────────────
function wire() {
  $("refresh").addEventListener("click", () => refresh());
  $("banner-retry").addEventListener("click", () => refresh());
  $("theme").addEventListener("click", toggleTheme);
  $("restock").addEventListener("click", () => (state.confirmRestock ? cancelRestock() : askRestock()));
  $("restock-no").addEventListener("click", cancelRestock);
  $("restock-yes").addEventListener("click", restock);
  $("restock-confirm").addEventListener("keydown", (e) => { if (e.key === "Escape") cancelRestock(); });
  for (const b of document.querySelectorAll(".tab")) b.addEventListener("click", () => showTab(b.dataset.tab));
  $("tabs").addEventListener("keydown", (e) => {
    const next = D.tabAfterKey(state.tab, e.key);
    if (!next) return;
    e.preventDefault();
    showTab(next);
    $(`tab-${next}`).focus();
  });
  // Back/forward and edited hashes switch the view; the URL is the source of truth.
  window.addEventListener("popstate", () => showTab(D.tabFromHash(location.hash), { push: false }));
  window.addEventListener("hashchange", () => showTab(D.tabFromHash(location.hash), { push: false }));
  for (const b of document.querySelectorAll(".story")) b.addEventListener("click", () => runScenario(b.dataset.scenario));
  $("demo-open").addEventListener("click", () => ($("demo-panel").hidden ? openDemo() : closeDemo()));
  $("demo-close").addEventListener("click", () => closeDemo());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("demo-panel").hidden && !state.confirmRestock) closeDemo();
  });
  document.addEventListener("click", (e) => {
    if (!$("demo-panel").hidden && !$("demo").contains(e.target)) closeDemo(false);
  });
  for (const b of document.querySelectorAll(".segmented__btn")) b.addEventListener("click", () => setFilter(b.dataset.filter));
  // Keep relative times ("12 s ago") fresh without polling the API.
  setInterval(() => { if (!document.hidden && state.loaded) { renderFlow(); renderOrders(); } }, 15000);
  syncThemeButton();
}

wire();
// ?focus= always lands on Live; otherwise the hash picks the view. A hash that asked for
// something else (or something unknown) is corrected in place, without a history entry.
const initialTab = params.get("focus") ? "live" : D.tabFromHash(location.hash);
showTab(initialTab, { push: false });
if (location.hash && location.hash !== `#${initialTab}`) {
  history.replaceState(null, "", `${location.pathname}${location.search}#${initialTab}`);
}
// View-only: ?demo=open opens the corner panel on load (handy for screenshots and links).
if (params.get("demo") === "open") openDemo();
if (!API) {
  state.error = new Error("no api");
  setText($("banner-text"), "No API address: deploy with sam deploy.");
  $("banner").hidden = false;
  renderLive(false);
} else {
  refresh();
}
