// Unit tests for dashboard/assets/derive.js (node --test, no dependencies).
import assert from "node:assert/strict";
import { test } from "node:test";

import * as D from "../../dashboard/assets/derive.js";

const listings = (qty = 5) => Object.fromEntries(D.MARKETS.map((m) => [m.id, {
  seller_sku: `MOCK-${m.code}`, price: 10, currency: m.currency, listed_qty: qty, sync_status: "seeded",
}]));
const product = (sku, stock, threshold = 5, extra = {}) => ({
  sku, title: sku, stock_on_hand: stock, low_stock_threshold: threshold, listings: listings(stock), ...extra,
});

test("product status uses units left and the warning level", () => {
  assert.equal(D.productStatus(product("A", 6, 5)), "ok");
  assert.equal(D.productStatus(product("A", 5, 5)), "ok");
  assert.equal(D.productStatus(product("A", 4, 5)), "low");
  assert.equal(D.productStatus(product("A", 0, 5)), "out");
  assert.equal(D.filterProducts([product("A", 9), product("B", 2), product("C", 0)], "low").length, 1);
});

test("summary counts every recent order and only USD-converted sales", () => {
  const orders = [
    { status: "COMPLETED", base_currency: "USD", base_total: 13.25 },
    { status: "COMPLETED", base_currency: "EUR", base_total: 11.99 }, // FX failed: not dollars
    { status: "REJECTED" }, { status: "REJECTED" }, { status: "RESERVED" },
  ];
  assert.deepEqual(D.summary(orders, [{}, {}]),
    { orders: 5, sold: 2, blocked: 2, lowWarnings: 2, salesUsd: 13.25 });
});

test("flow strip: blocked order stops at 'Check the shelf'", () => {
  const { states, notes } = D.flowStates({ status: "REJECTED", requested: 1, available: 0, quantity: 1 });
  assert.deepEqual(states, ["done", "blocked", "skipped", "skipped", "skipped", "skipped"]);
  assert.equal(notes[1], "Nobody was oversold.");
});

test("flow strip: completed order, with and without a low-stock warning", () => {
  const order = { order_id: "o1", status: "COMPLETED", sync_summary: { synced: 3, skipped: 1 } };
  assert.deepEqual(D.flowStates(order, []).states, Array(6).fill("done"));
  const warned = D.flowStates(order, [{ order_id: "o1", stock: 4 }]);
  assert.equal(warned.states[4], "warned");
  assert.match(warned.notes[4], /4 left/);
});

test("flow strip follows the workflow: stores are updated before the conversion", () => {
  assert.deepEqual(D.FLOW_STEPS.map((s) => s.key), ["in", "shelf", "shops", "fx", "low", "receipt"]);
  const order = { order_id: "o1", status: "COMPLETED", sync_summary: { synced: 3, skipped: 1 } };
  assert.equal(D.flowStates(order, []).notes[2], "3 updated, 1 already knew");
});

test("flow strip: an order whose conversion fell back still shows every step done", () => {
  const order = { order_id: "o2", status: "COMPLETED", currency: "EUR", fx_source: "fallback_error",
    base_currency: "EUR", base_total: "11.99", sync_summary: { synced: 3, skipped: 1 } };
  assert.deepEqual(D.flowStates(order, []).states, Array(6).fill("done"));
  assert.equal(D.usdTotal(order), null);
});

test("flow strip: accepted but not yet stored, and still processing", () => {
  assert.deepEqual(D.flowStates({ pending: true }).states.slice(0, 2), ["done", "running"]);
  assert.deepEqual(D.flowStates({ status: "RESERVED" }).states, ["done", "done", "running", "running", "running", "running"]);
  assert.deepEqual(D.flowStates(null).states, Array(6).fill("waiting"));
});

test("sell one in Germany picks the product with the most units", () => {
  const pick = D.pickSellOne([product("A", 3), product("B", 30), product("C", 0)]);
  assert.equal(pick.product.sku, "B");
  assert.deepEqual(pick.orders, [{ marketplace: "AMAZON_DE", quantity: 1 }]);
});

test("low-stock scenario takes the closest product just below its warning level", () => {
  const pick = D.pickLowStock([product("A", 20, 5), product("B", 6, 5), product("C", 3, 5)]);
  assert.equal(pick.product.sku, "B");
  assert.equal(pick.orders[0].quantity, 2); // 6 - 5 + 1: leaves 4, below 5
  assert.equal(D.pickLowStock([product("Z", 0, 5)]), null);
});

test("oversell asks for two more than the smallest in-stock product has", () => {
  const pick = D.pickOversell([product("A", 9), product("B", 3), product("C", 0)]);
  assert.equal(pick.product.sku, "B");
  assert.deepEqual(pick.orders, [{ marketplace: "AMAZON_UK", quantity: 5 }]);
});

test("race: two different shops, all units each, never more than two orders", () => {
  const pick = D.pickRace([product("A", 9), product("B", 1)], () => 0.3);
  assert.equal(pick.product.sku, "B");
  assert.equal(pick.orders.length, 2);
  assert.notEqual(pick.orders[0].marketplace, pick.orders[1].marketplace);
  assert.ok(pick.orders.every((o) => o.quantity === 1));
});

test("race order is not biased: every shop is sent first sometimes", () => {
  let seed = 42;
  const rng = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const firsts = {};
  for (let i = 0; i < 400; i += 1) {
    const [first] = D.raceOrders(product("B", 1), rng);
    firsts[first.marketplace] = (firsts[first.marketplace] || 0) + 1;
  }
  assert.equal(Object.keys(firsts).length, 4);
  for (const n of Object.values(firsts)) assert.ok(n > 60, JSON.stringify(firsts)); // ~100 each
});

test("nothing to pick when everything is sold out", () => {
  const ps = [product("A", 0), product("B", 0)];
  assert.equal(D.pickSellOne(ps), null);
  assert.equal(D.pickRace(ps), null);
  assert.equal(D.pickOversell(ps), null);
});

test("plain-language wording", () => {
  assert.deepEqual(D.orderStatus({ status: "COMPLETED" }), { key: "sold", text: "Sold" });
  assert.equal(D.orderStatus({ status: "REJECTED" }).text, "Blocked");
  assert.equal(D.orderStatus({ status: "RESERVED" }).text, "Processing");
  assert.equal(D.blockedSentence({ requested: 5, available: 3 }), "Wanted 5, only 3 left.");
  assert.equal(D.fxNote({ status: "COMPLETED", fx_source: "ECB", fx_date: "2026-11-13" }),
    "ECB rate of 2026-11-13");
  assert.equal(D.fxNote({ status: "COMPLETED", fx_source: "identity" }), "");
  assert.equal(D.usdTotal({ status: "COMPLETED", base_currency: "EUR", base_total: 5 }), null);
});

test("money, quantities and the focused product", () => {
  assert.equal(D.formatMoney(1249.99, "TRY"), "₺1,249.99");
  assert.equal(D.formatMoney(9.5, "GBP"), "£9.50");
  assert.equal(D.clampQty("0"), 1);
  assert.equal(D.clampQty("250"), 100);
  assert.equal(D.clampQty("abc"), 1);
  const ps = [product("A", 9), product("B", 2), product("C", 0)];
  assert.equal(D.focusProduct(ps, null, null).sku, "B"); // fresh seed: fewest units in stock
  assert.equal(D.focusProduct(ps, { sku: "A" }, "B").sku, "A");
  assert.equal(D.productImage("OCTO-MUG-001"), "assets/img/products/octo-mug-001.webp");
});

test("in-stock products come first, order kept inside each group", () => {
  const ps = [product("A", 0), product("B", 3), product("C", 0), product("D", 9)];
  assert.deepEqual(D.inStockFirst(ps).map((p) => p.sku), ["B", "D", "A", "C"]);
});

test("data from an older version (no current store listings) is detected", () => {
  const old = { sku: "A", stock_on_hand: 5, listings: { EBAY_DE: { listed_qty: 5 } } };
  assert.equal(D.hasNoKnownListings([old]), true);
  assert.equal(D.hasNoKnownListings([old, product("B", 3)]), false);
  assert.equal(D.pickSellOne([old]), null); // nothing to sell until restocked
});
