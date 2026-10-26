// Run from the frontend/ folder with: node --test   (Node 20+, no dependencies)
import assert from "node:assert/strict";
import test from "node:test";

import { getSession, login } from "../shared/js/auth.js";
import { ApiError, api, request } from "../shared/js/api.js";
import { displayName, hasRole, pickMembership, safeNext } from "../restaurant-dashboard/js/session.js";

const json = (body, init = {}) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json", ...(init.headers ?? {}) }, ...init });

function setup(handler) {
  const calls = [];
  globalThis.document = { cookie: "" };
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return handler(url, init, calls);
  };
  return calls;
}

test("GET: same-origin, JSON, no CSRF header", async () => {
  const calls = setup(() => json({ ok: true }));
  document.cookie = "csrftoken=tok123";
  assert.deepEqual(await api.get("/auth/me/"), { ok: true });
  assert.equal(calls[0].url, "/api/v1/auth/me/");
  assert.equal(calls[0].init.credentials, "same-origin");
  assert.equal(calls[0].init.headers["X-CSRFToken"], undefined);
});

test("POST: JSON body and CSRF token from the cookie", async () => {
  const calls = setup(() => json({ ok: true }));
  document.cookie = "other=1; csrftoken=tok%20123";
  await api.post("/auth/login/", { email: "a@b.co" });
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.body, '{"email":"a@b.co"}');
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.equal(calls[0].init.headers["X-CSRFToken"], "tok 123");
});

test("204 resolves to null", async () => {
  setup(() => new Response(null, { status: 204 }));
  assert.equal(await api.post("/auth/logout/"), null);
});

test("error envelope becomes an ApiError", async () => {
  setup(() => json({ error: { code: "not_a_member", message: "No access.", details: { x: 1 } } }, { status: 403 }));
  await assert.rejects(api.get("/x/"), (err) => {
    assert.ok(err instanceof ApiError);
    assert.deepEqual([err.status, err.code, err.message, err.details], [403, "not_a_member", "No access.", { x: 1 }]);
    return true;
  });
});

test("429 exposes Retry-After seconds", async () => {
  setup(() => json({ error: { code: "throttled", message: "Slow down." } }, { status: 429, headers: { "Retry-After": "30" } }));
  await assert.rejects(api.post("/auth/login/", {}), (err) => err.status === 429 && err.retryAfter === 30);
});

test("an HTML error page does not leak into the UI", async () => {
  setup(() => new Response("<html>Bad gateway</html>", { status: 502 }));
  await assert.rejects(api.get("/x/"), (err) => err.status === 502 && err.code === "http_error" && !err.message.includes("<"));
});

test("a 200 that is not JSON is rejected (wrong base URL)", async () => {
  setup(() => new Response("<html>index</html>", { status: 200 }));
  await assert.rejects(api.get("/x/"), (err) => err.code === "invalid_response");
});

test("network failure becomes network_error with status 0", async () => {
  setup(() => Promise.reject(new TypeError("fetch failed")));
  await assert.rejects(api.get("/x/"), (err) => err.code === "network_error" && err.status === 0);
});

test("timeout aborts the request", async () => {
  setup((url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))));
  await assert.rejects(request("/x/", { timeoutMs: 20 }), (err) => err instanceof ApiError && err.code === "timeout");
});

test("caller cancellation surfaces as AbortError, not ApiError", async () => {
  setup((url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))));
  const controller = new AbortController();
  const pending = request("/x/", { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, (err) => err.name === "AbortError" && !(err instanceof ApiError));
});

test("getSession: null on 401, data on 200, throws otherwise", async () => {
  setup(() => json({ error: { code: "not_authenticated", message: "x" } }, { status: 401 }));
  assert.equal(await getSession(), null);
  setup(() => json({ user: { email: "a@b.co" }, memberships: [] }));
  assert.equal((await getSession()).user.email, "a@b.co");
  setup(() => json({ error: { code: "error", message: "x" } }, { status: 500 }));
  await assert.rejects(getSession(), (err) => err.status === 500);
});

test("login fetches the CSRF cookie first, then posts credentials", async () => {
  const calls = setup((url) => (url.endsWith("/auth/csrf/") ? new Response(null, { status: 204 }) : json({ user: {}, memberships: [] })));
  await login("a@b.co", "pw");
  assert.deepEqual(calls.map((c) => [c.init.method, c.url]), [["GET", "/api/v1/auth/csrf/"], ["POST", "/api/v1/auth/login/"]]);
  assert.equal(calls[1].init.body, '{"email":"a@b.co","password":"pw"}');
});

test("role checks fail closed", () => {
  assert.ok(hasRole("OWNER", "MANAGER") && hasRole("MANAGER", "MANAGER"));
  assert.ok(!hasRole("STAFF", "MANAGER"));
  assert.ok(!hasRole("BOSS", "STAFF") && !hasRole("OWNER", "SUPERUSER") && !hasRole(undefined, "STAFF"));
});

test("safeNext only allows known dashboard pages", () => {
  assert.equal(safeNext("team.html"), "team.html");
  for (const bad of ["https://evil.example", "//evil.example", "../x.html", "javascript:alert(1)", "", null]) {
    assert.equal(safeNext(bad), "index.html");
  }
});

test("membership and name helpers", () => {
  const a = { restaurant: { slug: "a" }, role: "STAFF" };
  const b = { restaurant: { slug: "b" }, role: "OWNER" };
  assert.equal(pickMembership([a, b], "b"), b);
  assert.equal(pickMembership([a, b], "gone"), a);
  assert.equal(pickMembership([], "a"), null);
  assert.equal(displayName({ first_name: "Ada", last_name: "Obi", email: "x@y.co" }), "Ada Obi");
  assert.equal(displayName({ first_name: "", last_name: "", email: "x@y.co" }), "x@y.co");
});
