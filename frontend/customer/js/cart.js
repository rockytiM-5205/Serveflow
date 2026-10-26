/* The customer's cart: item ids and quantities only. Prices are never stored; the menu supplies
 * them each time, and the server prices the real order. */
const MAX_QUANTITY = 99;
const MAX_LINES = 30;

const storageKey = (slug) => `serveflow.cart.${slug}`;

/** "2.50" -> 250. Works on the decimal strings the API sends, with no floating-point maths. */
export function toCents(price) {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(String(price));
  if (!match) return 0;
  return Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0") || 0);
}

export function fromCents(cents) {
  const whole = Math.trunc(cents / 100);
  return `${whole}.${String(cents % 100).padStart(2, "0")}`;
}

export function clampQuantity(value) {
  const n = Math.trunc(Number(value));
  return Number.isFinite(n) ? Math.min(MAX_QUANTITY, Math.max(0, n)) : 0;
}

function readLines(storage, slug) {
  try {
    const parsed = JSON.parse(storage.getItem(storageKey(slug)) ?? "null");
    if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.lines)) return [];
    return parsed.lines
      .filter((line) => Array.isArray(line) && Number.isInteger(line[0]) && line[0] > 0)
      .map(([id, quantity]) => [id, clampQuantity(quantity)])
      .filter(([, quantity]) => quantity > 0)
      .slice(0, MAX_LINES);
  } catch {
    return [];
  }
}

/** A small observable store, saved to the given storage so the cart survives page changes. */
export function createCart(slug, storage = globalThis.localStorage) {
  const quantities = new Map(readLines(storage, slug));
  const listeners = new Set();

  const persist = () => {
    try {
      storage.setItem(storageKey(slug), JSON.stringify({ v: 1, lines: [...quantities] }));
    } catch {
      /* storage unavailable: the cart lives for this page only */
    }
    listeners.forEach((fn) => fn());
  };

  return {
    quantity: (id) => quantities.get(id) ?? 0,
    entries: () => [...quantities],
    count: () => [...quantities.values()].reduce((sum, q) => sum + q, 0),
    set(id, quantity) {
      const q = clampQuantity(quantity);
      if (q === 0) quantities.delete(id);
      else if (quantities.has(id) || quantities.size < MAX_LINES) quantities.set(id, q);
      persist();
    },
    change(id, delta) {
      this.set(id, this.quantity(id) + delta);
    },
    /** Drop lines whose items are missing or unavailable in `itemsById`. Returns the removed ids. */
    reconcile(itemsById) {
      const removed = [...quantities.keys()].filter((id) => !itemsById.get(id)?.is_available);
      removed.forEach((id) => quantities.delete(id));
      if (removed.length) persist();
      return removed;
    },
    remove(ids) {
      ids.forEach((id) => quantities.delete(id));
      persist();
    },
    clear() {
      quantities.clear();
      persist();
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

/** Cart lines joined with menu items, plus an estimated total in cents (display only). */
export function describeCart(cart, itemsById) {
  const lines = cart.entries()
    .filter(([id]) => itemsById.has(id))
    .map(([id, quantity]) => {
      const item = itemsById.get(id);
      return { id, item, quantity, lineCents: toCents(item.price) * quantity };
    });
  return { lines, totalCents: lines.reduce((sum, line) => sum + line.lineCents, 0) };
}

// ---- remembering the last order so the customer can find it again ----
const lastOrderKey = (slug) => `serveflow.lastOrder.${slug}`;
export const saveLastOrder = (slug, token, storage = globalThis.localStorage) => {
  try { storage.setItem(lastOrderKey(slug), token); } catch { /* ignore */ }
};
export const loadLastOrder = (slug, storage = globalThis.localStorage) => {
  try {
    const token = storage.getItem(lastOrderKey(slug));
    return /^[0-9a-f]{96}$/.test(token ?? "") ? token : null;
  } catch {
    return null;
  }
};

// ---- Idempotency-Key: one key per distinct order attempt, reused when the same order is retried ----
export function idempotencyKeyFor(slug, payload, storage = globalThis.sessionStorage) {
  const fingerprint = JSON.stringify(payload);
  const name = `serveflow.idem.${slug}`;
  try {
    const saved = JSON.parse(storage.getItem(name) ?? "null");
    if (saved?.fingerprint === fingerprint && /^[A-Za-z0-9_-]{16,64}$/.test(saved.key)) return saved.key;
  } catch { /* fall through to a new key */ }
  const key = globalThis.crypto.randomUUID().replaceAll("-", "");
  try { storage.setItem(name, JSON.stringify({ fingerprint, key })); } catch { /* ignore */ }
  return key;
}

export function clearIdempotencyKey(slug, storage = globalThis.sessionStorage) {
  try { storage.removeItem(`serveflow.idem.${slug}`); } catch { /* ignore */ }
}
