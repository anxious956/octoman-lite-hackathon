// Pure functions: API data in, plain values out. No DOM, no network, no clock
// unless passed in. app.js renders what these return; tests/js covers them.

export const MARKETS = [
  { id: "AMAZON_US", code: "US", name: "United States", store: "amazon.com", flag: "us", currency: "USD", symbol: "$" },
  { id: "AMAZON_UK", code: "UK", name: "United Kingdom", store: "amazon.co.uk", flag: "gb", currency: "GBP", symbol: "£" },
  { id: "AMAZON_DE", code: "DE", name: "Germany", store: "amazon.de", flag: "de", currency: "EUR", symbol: "€" },
  { id: "AMAZON_TR", code: "TR", name: "Türkiye", store: "amazon.com.tr", flag: "tr", currency: "TRY", symbol: "₺" },
];
export const MARKET_BY_ID = Object.fromEntries(MARKETS.map((m) => [m.id, m]));
export const MAX_QTY = 100;

// ── products ────────────────────────────────────────────────────────

export function unitsLeft(p) {
  return Math.max(0, Number(p.stock_on_hand) || 0);
}

export function warnBelow(p) {
  return Number(p.low_stock_threshold) || 0;
}

/** "out" | "low" | "ok" */
export function productStatus(p) {
  const left = unitsLeft(p);
  if (left <= 0) return "out";
  if (left < warnBelow(p)) return "low";
  return "ok";
}

export const STATUS_TEXT = { ok: "In stock", low: "Running low", out: "Sold out" };

export function filterProducts(products, filter) {
  if (filter === "low") return products.filter((p) => productStatus(p) === "low");
  if (filter === "out") return products.filter((p) => productStatus(p) === "out");
  return products;
}

/** True when no product has a listing on any current store (data from an older version). */
export function hasNoKnownListings(products) {
  return products.every((p) => !MARKETS.some((m) => p.listings && p.listings[m.id]));
}

/** In-stock products first, sold-out last; keeps the original order inside each group. */
export function inStockFirst(products) {
  return [...products.filter((p) => unitsLeft(p) > 0), ...products.filter((p) => unitsLeft(p) <= 0)];
}

export function productImage(sku) {
  return `assets/img/products/${String(sku).toLowerCase()}.svg`;
}

export function formatMoney(amount, currency) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "";
  const m = MARKETS.find((x) => x.currency === currency);
  const fixed = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return m ? `${m.symbol}${fixed}` : `${fixed} ${currency || ""}`.trim();
}

// ── orders ──────────────────────────────────────────────────────────

/** Plain-language status for an order row. */
export function orderStatus(o) {
  if (o.status === "COMPLETED") return { key: "sold", text: "Sold" };
  if (o.status === "REJECTED") return { key: "blocked", text: "Blocked: not enough stock" };
  return { key: "processing", text: "Processing" };
}

export function blockedSentence(o) {
  const wanted = Number(o.requested ?? o.quantity) || 0;
  const left = Number(o.available) || 0;
  return `Oversell prevented: wanted ${wanted}, only ${left} left.`;
}

/** Short note about the currency conversion, or "" when none is needed. */
export function fxNote(o) {
  if (o.status !== "COMPLETED") return "";
  if (o.fx_source === "ECB") return `converted at the ECB rate of ${o.fx_date}`;
  if (o.fx_source === "fallback") return "converted at a saved rate";
  if (o.fx_source === "fallback_error") return "not converted (rate service unavailable)";
  return "";
}

/** USD amount to show, or null when the order was not converted to USD. */
export function usdTotal(o) {
  if (o.status !== "COMPLETED" || o.base_currency !== "USD") return null;
  const n = Number(o.base_total);
  return Number.isFinite(n) ? n : null;
}

/**
 * The one-line summary over the recent orders the API returns (up to 100):
 * orders, sold, oversells blocked, low-stock warnings, sales in USD.
 * Not limited to "today": judges open the page days after the demo orders.
 */
export function summary(orders, alerts) {
  const sold = orders.filter((o) => o.status === "COMPLETED");
  return {
    orders: orders.length,
    sold: sold.length,
    blocked: orders.filter((o) => o.status === "REJECTED").length,
    lowWarnings: alerts.length,
    salesUsd: Math.round(sold.reduce((sum, o) => sum + (usdTotal(o) ?? 0), 0) * 100) / 100,
  };
}

// ── flow strip ──────────────────────────────────────────────────────

export const FLOW_STEPS = [
  { key: "in", name: "Order arrives", caption: "API Gateway + Lambda", icon: "shopping-bag" },
  { key: "shelf", name: "Check the shelf", caption: "DynamoDB transaction", icon: "package" },
  { key: "fx", name: "Convert to dollars", caption: "Lambda + ECB rates", icon: "circle-dollar-sign" },
  { key: "shops", name: "Update all 4 stores", caption: "Step Functions Parallel", icon: "store" },
  { key: "low", name: "Low-stock warning", caption: "DynamoDB", icon: "triangle-alert" },
  { key: "receipt", name: "Save receipt", caption: "S3", icon: "receipt" },
];

/**
 * Node states for the flow strip: "waiting" | "running" | "done" | "blocked" | "skipped" | "warned".
 * `order` is an order from GET /orders, or {pending: true} for one the API accepted but
 * that is not in /orders yet. Returns {states, notes} with one entry per FLOW_STEPS item.
 */
export function flowStates(order, alerts = []) {
  const n = FLOW_STEPS.length;
  const notes = Array(n).fill("");
  if (!order) return { states: Array(n).fill("waiting"), notes };
  if (order.pending) {
    return { states: ["done", "running", "waiting", "waiting", "waiting", "waiting"], notes };
  }
  if (order.status === "REJECTED") {
    const wanted = Number(order.requested ?? order.quantity) || 0;
    const left = Number(order.available) || 0;
    notes[1] = `Stopped here. ${wanted} wanted, ${left} left. Nobody was oversold.`;
    return { states: ["done", "blocked", "skipped", "skipped", "skipped", "skipped"], notes };
  }
  if (order.status === "COMPLETED") {
    const states = Array(n).fill("done");
    const alert = alerts.find((a) => a.order_id === order.order_id);
    if (alert) {
      states[4] = "warned";
      notes[4] = Number(alert.stock) <= 0 ? "Warning raised: sold out" : `Warning raised: ${alert.stock} left`;
    } else {
      notes[4] = "Stock still fine";
    }
    const s = order.sync_summary || {};
    notes[3] = `${s.synced ?? 0} updated, ${s.skipped ?? 0} already knew`;
    return { states, notes };
  }
  return { states: ["done", "done", "running", "running", "running", "running"], notes };
}

// ── guided scenarios ("Try it") ─────────────────────────────────────

function listedOn(p, marketId) {
  return Boolean(p.listings && p.listings[marketId]);
}

function inStock(products) {
  return products.filter((p) => unitsLeft(p) > 0);
}

/** "A customer in Germany buys one": the product with the most units left. */
export function pickSellOne(products) {
  const c = inStock(products).filter((p) => listedOn(p, "AMAZON_DE"));
  if (!c.length) return null;
  const p = c.reduce((a, b) => (unitsLeft(b) > unitsLeft(a) ? b : a));
  return { product: p, orders: [{ marketplace: "AMAZON_DE", quantity: 1 }] };
}

/** "Sell until stock runs low": smallest non-negative gap to the warning level. */
export function pickLowStock(products) {
  const c = inStock(products)
    .filter((p) => listedOn(p, "AMAZON_US") && warnBelow(p) >= 1 && unitsLeft(p) >= warnBelow(p))
    .filter((p) => unitsLeft(p) - warnBelow(p) + 1 <= Math.min(unitsLeft(p), MAX_QTY));
  if (!c.length) return null;
  const gap = (p) => unitsLeft(p) - warnBelow(p);
  const p = c.reduce((a, b) => (gap(b) < gap(a) ? b : a));
  return { product: p, orders: [{ marketplace: "AMAZON_US", quantity: gap(p) + 1 }] };
}

/** "Two customers buy the last one at once": the in-stock product with the fewest units. */
export function pickRace(products, rng = Math.random) {
  const c = inStock(products).filter((p) => MARKETS.filter((m) => listedOn(p, m.id)).length >= 2);
  if (!c.length) return null;
  const p = c.reduce((a, b) => (unitsLeft(b) < unitsLeft(a) ? b : a));
  return { product: p, orders: raceOrders(p, rng) };
}

/** Two orders from two different random sites, each for every unit left, in random order. */
export function raceOrders(product, rng = Math.random) {
  const sites = shuffle(MARKETS.filter((m) => listedOn(product, m.id)).map((m) => m.id), rng).slice(0, 2);
  const qty = Math.min(Math.max(1, unitsLeft(product)), MAX_QTY);
  return sites.map((marketplace) => ({ marketplace, quantity: qty }));
}

/** "Someone orders more than we have": the smallest in-stock product, two more than it has. */
export function pickOversell(products) {
  const c = inStock(products).filter((p) => listedOn(p, "AMAZON_UK") && unitsLeft(p) + 1 <= MAX_QTY);
  if (!c.length) return null;
  const p = c.reduce((a, b) => (unitsLeft(b) < unitsLeft(a) ? b : a));
  return { product: p, orders: [{ marketplace: "AMAZON_UK", quantity: Math.min(unitsLeft(p) + 2, MAX_QTY) }] };
}

/** Fisher-Yates with an injectable random source (tests pass a seeded one). */
export function shuffle(items, rng = Math.random) {
  const a = items.slice();
  for (let i = a.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** Which product the shelf picture shows. */
export function focusProduct(products, focusedOrder, lastSku) {
  const bySku = (sku) => products.find((p) => p.sku === sku);
  if (focusedOrder && bySku(focusedOrder.sku)) return bySku(focusedOrder.sku);
  if (lastSku && bySku(lastSku)) return bySku(lastSku);
  // Otherwise the most recently changed product; on a fresh seed (all equal) the
  // in-stock product with the fewest units, so the countable units are visible.
  const rank = (p) => (unitsLeft(p) > 0 ? unitsLeft(p) : Number.MAX_SAFE_INTEGER);
  return products.slice().sort((a, b) =>
    String(b.updated_at || "").localeCompare(String(a.updated_at || "")) || rank(a) - rank(b))[0] || null;
}

export function clampQty(v) {
  const n = Math.floor(Number(v));
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.min(n, MAX_QTY);
}

export function timeAgo(iso, now = Date.now()) {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(t).toLocaleDateString();
}
