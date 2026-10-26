// Pure helper tests. Run from the frontend/ folder with: node --test
import assert from "node:assert/strict";
import test from "node:test";

import { isHttpsUrl, isValidEmail, isValidPrice, isValidSlug, isValidSortOrder, slugify } from "../shared/js/validators.js";
import { parseSlug, telHref } from "../customer/js/helpers.js";
import { safeNext } from "../restaurant-dashboard/js/session.js";

test("parseSlug accepts well-formed slugs and lowercases them", () => {
  assert.equal(parseSlug("?r=green-bowl"), "green-bowl");
  assert.equal(parseSlug("?r=Green-Bowl"), "green-bowl");
  assert.equal(parseSlug("?x=1&r=abc"), "abc");
});

test("parseSlug rejects missing or malformed slugs", () => {
  for (const search of ["", "?r=", "?r=ab", "?r=-bad", "?r=bad-", "?r=a--b", "?r=has space", "?r=a/b", "?r=../x", `?r=${"a".repeat(64)}`]) {
    assert.equal(parseSlug(search), null, search);
  }
});

test("telHref only ever builds a tel: link from digits and plus", () => {
  assert.equal(telHref("+44 (0)20 7946-0958"), "tel:+4402079460958");
  assert.equal(telHref("javascript:alert(1)"), "tel:1");
  assert.equal(telHref("call us"), null);
  assert.equal(telHref(""), null);
  assert.equal(telHref(null), null);
});

test("isHttpsUrl", () => {
  assert.ok(isHttpsUrl("https://cdn.example.com/a.jpg"));
  for (const bad of ["http://a.com/x.jpg", "javascript:alert(1)", "data:image/png;base64,AA", "//a.com/x.jpg", "https://", "", null, undefined, 5]) {
    assert.ok(!isHttpsUrl(bad), String(bad));
  }
});

test("isValidPrice matches what the backend accepts", () => {
  for (const ok of ["0", "5", "2.5", "12.50", "99999999.99"]) assert.ok(isValidPrice(ok), ok);
  for (const bad of ["", "-1", "1.234", "abc", "1,5", "123456789", ".5", "5.", " 5"]) assert.ok(!isValidPrice(bad), bad);
});

test("isValidSortOrder", () => {
  assert.ok(isValidSortOrder(0) && isValidSortOrder(32767));
  for (const bad of [-1, 32768, 1.5, NaN, null]) assert.ok(!isValidSortOrder(bad), String(bad));
});

test("safeNext knows the menu page", () => {
  assert.equal(safeNext("menu.html"), "menu.html");
  assert.equal(safeNext("https://evil.example"), "index.html");
});

test("slugify produces valid slugs", () => {
  assert.equal(slugify("Green Bowl & Grill"), "green-bowl-grill");
  assert.equal(slugify("  Café Délice!  "), "cafe-delice");
  assert.equal(slugify("---"), "");
  assert.equal(slugify("a".repeat(100)).length, 63);
  assert.ok(!slugify(`${"a".repeat(62)} b`).endsWith("-"));
  for (const name of ["Green Bowl", "Mama's Kitchen #2", "Ünïcode Eats"]) assert.ok(isValidSlug(slugify(name)), name);
});

test("isValidSlug and isValidEmail", () => {
  assert.ok(isValidSlug("green-bowl") && isValidSlug("abc"));
  for (const bad of ["ab", "-a-", "a--b", "Ab c", "a_b", "", null]) assert.ok(!isValidSlug(bad), String(bad));
  assert.ok(isValidEmail("a@b.co"));
  for (const bad of ["a@b", "a b@c.co", "@b.co", "", null]) assert.ok(!isValidEmail(bad), String(bad));
});

test("safeNext knows the new pages", () => {
  assert.equal(safeNext("settings.html"), "settings.html");
  assert.equal(safeNext("create-restaurant.html"), "create-restaurant.html");
});

// ---- cart, ordering helpers ----
import { clampQuantity, createCart, describeCart, fromCents, idempotencyKeyFor, loadLastOrder, saveLastOrder, toCents } from "../customer/js/cart.js";
import { HEADLINE, isTerminal, timelineSteps, tokenFromHash } from "../customer/js/order-view.js";
import { formatClock, timeAgo } from "../restaurant-dashboard/js/time.js";

const fakeStorage = () => {
  const data = new Map();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: (k) => data.delete(k), data };
};

test("money is handled in whole cents, never floats", () => {
  assert.equal(toCents("2.50"), 250);
  assert.equal(toCents("0.10"), 10);
  assert.equal(toCents("7"), 700);
  assert.equal(toCents("19.9"), 1990);
  assert.equal(toCents("abc"), 0);
  assert.equal(fromCents(250), "2.50");
  assert.equal(fromCents(5), "0.05");
  assert.equal(fromCents(toCents("0.10") * 3), "0.30"); // 0.1 * 3 would be 0.30000000000000004 as a float
});

test("quantities are clamped to 0-99", () => {
  assert.deepEqual([clampQuantity(5), clampQuantity(-3), clampQuantity(500), clampQuantity("x"), clampQuantity(2.9)], [5, 0, 99, 0, 2]);
});

test("the cart keeps ids and quantities, survives reloads and ignores corrupt storage", () => {
  const storage = fakeStorage();
  const cart = createCart("green-bowl", storage);
  cart.change(7, 1);
  cart.change(7, 1);
  cart.set(9, 3);
  assert.equal(cart.quantity(7), 2);
  assert.equal(cart.count(), 5);
  assert.deepEqual(JSON.parse(storage.data.get("serveflow.cart.green-bowl")), { v: 1, lines: [[7, 2], [9, 3]] });
  assert.equal(createCart("green-bowl", storage).count(), 5); // a new page load
  assert.equal(createCart("other-place", storage).count(), 0); // carts are per restaurant

  cart.change(7, -5);
  assert.equal(cart.quantity(7), 0);
  assert.equal(cart.entries().length, 1);

  for (const junk of ["not json", '{"v":2,"lines":[]}', '{"v":1,"lines":[["x",1],[3,"y"],[-1,2],[4,0],[5,9999]]}']) {
    const s = fakeStorage();
    s.setItem("serveflow.cart.p", junk);
    assert.ok(createCart("p", s).count() <= 99, junk);
  }
});

test("the cart is capped at 99 per item", () => {
  const cart = createCart("p", fakeStorage());
  cart.set(1, 98);
  cart.change(1, 5);
  assert.equal(cart.quantity(1), 99);
});

test("reconcile drops items that are gone or unavailable", () => {
  const cart = createCart("p", fakeStorage());
  cart.set(1, 1); cart.set(2, 1); cart.set(3, 1);
  const menu = new Map([[1, { id: 1, is_available: true }], [2, { id: 2, is_available: false }]]);
  assert.deepEqual(cart.reconcile(menu).sort(), [2, 3]);
  assert.deepEqual(cart.entries(), [[1, 1]]);
});

test("the estimated total uses menu prices", () => {
  const cart = createCart("p", fakeStorage());
  cart.set(1, 3); cart.set(2, 2);
  const menu = new Map([[1, { id: 1, price: "2.50" }], [2, { id: 2, price: "1.25" }]]);
  const { lines, totalCents } = describeCart(cart, menu);
  assert.equal(totalCents, 1000);
  assert.deepEqual(lines.map((l) => l.lineCents), [750, 250]);
});

test("cart subscribers are told about changes", () => {
  const cart = createCart("p", fakeStorage());
  let calls = 0;
  const off = cart.subscribe(() => calls++);
  cart.set(1, 1); cart.clear();
  off(); cart.set(1, 1);
  assert.equal(calls, 2);
});

test("the last order token is only remembered when it looks like a token", () => {
  const s = fakeStorage();
  saveLastOrder("p", "0".repeat(96), s);
  assert.equal(loadLastOrder("p", s), "0".repeat(96));
  saveLastOrder("p", "nonsense", s);
  assert.equal(loadLastOrder("p", s), null);
});

test("a retried order reuses its idempotency key; a changed order gets a new one", () => {
  const s = fakeStorage();
  const order = { items: [{ menu_item_id: 1, quantity: 2 }], customer_name: "Ada" };
  const first = idempotencyKeyFor("p", order, s);
  assert.match(first, /^[A-Za-z0-9_-]{16,64}$/);
  assert.equal(idempotencyKeyFor("p", { ...order }, s), first);
  assert.notEqual(idempotencyKeyFor("p", { ...order, customer_name: "Bo" }, s), first);
});

test("order links come only from a well-formed fragment", () => {
  const token = "ab".repeat(48);
  assert.equal(tokenFromHash(`#${token}`), token);
  for (const bad of ["", "#", "#short", `#${token}0`, `#${token.toUpperCase()}`, null]) assert.equal(tokenFromHash(bad), null, String(bad));
});

test("the order timeline follows the status", () => {
  const order = (status, reached) => ({ status, timeline: reached.map((s) => ({ status: s })) });
  const steps = timelineSteps(order("SERVING", ["PENDING", "CONFIRMED", "SERVING"]));
  assert.deepEqual(steps.map((s) => [s.done, s.current]), [[true, false], [true, false], [true, true], [false, false]]);
  const cancelled = timelineSteps(order("CANCELLED", ["PENDING", "CANCELLED"]));
  assert.ok(cancelled.every((s) => !s.current));
  assert.ok(isTerminal("SERVED") && isTerminal("REJECTED") && !isTerminal("PENDING"));
  for (const status of ["PENDING", "CONFIRMED", "SERVING", "SERVED", "REJECTED", "CANCELLED"]) assert.ok(HEADLINE[status], status);
});

test("time wording", () => {
  const now = Date.parse("2026-10-26T12:00:00Z");
  assert.equal(timeAgo("2026-10-26T11:59:40Z", now), "just now");
  assert.equal(timeAgo("2026-10-26T11:55:00Z", now), "5 min ago");
  assert.equal(timeAgo("2026-10-26T09:00:00Z", now), "3 h ago");
  assert.equal(timeAgo("2026-10-24T12:00:00Z", now), "2 d ago");
  assert.equal(timeAgo("garbage", now), "just now");
  assert.equal(formatClock("2026-10-26T12:05:00Z", "UTC", "en-GB"), "12:05");
  assert.equal(formatClock("2026-10-26T12:05:00Z", "Not/AZone", "en-GB"), "");
});
