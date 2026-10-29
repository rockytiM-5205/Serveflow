import { ApiError, api } from "../../shared/js/api.js";
import { closeOnBackdrop, el, emptyState, formatMoney, icon, setBusy, toast } from "../../shared/js/ui.js";
import { formDialog } from "./form-dialog.js";
import { attachBadge, defaultShouldSkip, liveBadge, startLive } from "../../shared/js/live.js";
import { ROLE_LABEL, hasRole } from "./session.js";
import { bootDashboard, handleSessionExpiry } from "./shell.js";
import { formatClock, formatDateTime, timeAgo } from "./time.js";

const HREF = "orders.html";
const POLL_MS = 15000;
const FILTERS = [
  { id: "queue", label: "Needs attention", params: { queue: "1" }, empty: "Nothing needs attention right now." },
  { id: "pending", label: "Pending", params: { status: "PENDING" }, empty: "No orders are waiting for confirmation." },
  { id: "progress", label: "In progress", params: { status: "CONFIRMED,SERVING" }, empty: "No orders are being prepared." },
  { id: "finished", label: "Finished", params: { status: "SERVED,REJECTED,CANCELLED" }, empty: "No finished orders yet." },
  { id: "all", label: "All", params: {}, empty: "No orders yet." },
];
const STATUS_LABEL = { PENDING: "Pending", CONFIRMED: "Confirmed", SERVING: "Being served", SERVED: "Served", REJECTED: "Rejected", CANCELLED: "Cancelled" };
const ACTOR_LABEL = { CUSTOMER: "Customer", STAFF: "Staff", MANAGER: "Manager", OWNER: "Owner", SYSTEM: "System" };

const content = document.getElementById("content");
const SOUND_STORAGE_KEY = "serveflow.sound";
const soundWanted = () => {
  try { return localStorage.getItem(SOUND_STORAGE_KEY) === "on"; } catch { return false; }
};
let audio = null;
/** Two short beeps. The audio context is created from a click, which browsers require. */
function chime() {
  if (!audio) return;
  [0, 0.22].forEach((offset) => {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, audio.currentTime + offset);
    gain.gain.exponentialRampToValueAtTime(0.25, audio.currentTime + offset + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + offset + 0.18);
    osc.connect(gain).connect(audio.destination);
    osc.start(audio.currentTime + offset);
    osc.stop(audio.currentTime + offset + 0.2);
  });
}
const newKey = () => crypto.randomUUID().replaceAll("-", "");

async function main() {
  const ctx = await bootDashboard({ href: HREF });
  if (!ctx) return;
  const isManager = hasRole(ctx.role, "MANAGER");
  const base = `/restaurants/${encodeURIComponent(ctx.restaurant.slug)}`;
  let info = { currency: "USD", timezone: "UTC" };
  let filter = FILTERS[0];
  let orders = [];
  let nextQuery = null;
  let known = null; // ids seen so far, to spot new orders
  let loadedMore = false; // "Load more" pages are not live: refreshing would collapse them

  const failure = (err) => {
    if (handleSessionExpiry(err, HREF)) return;
    if (err instanceof ApiError && err.code === "stale_status") {
      toast("Someone else just updated this order. Showing the latest.", { type: "info" });
      refresh();
      return;
    }
    toast(err instanceof ApiError ? err.message : "Something went wrong.", { type: "error" });
  };

  const query = (extra = {}) => `?${new URLSearchParams({ ...filter.params, ...extra })}`;

  /** Fetch and draw the newest orders. Throws on failure. `announce` flags new ones (toast, and a chime if switched on). */
  async function load({ announce = false } = {}) {
    const page = await api.get(`${base}/orders/${query({ page_size: 100 })}`);
    const fresh = page.results.filter((o) => known && !known.has(o.public_id) && o.status === "PENDING");
    known = new Set([...(known ?? []), ...page.results.map((o) => o.public_id)]);
    orders = page.results;
    loadedMore = false;
    nextQuery = page.next ? new URL(page.next, location.href).search : null;
    render(new Set(fresh.map((o) => o.public_id)));
    if (announce && fresh.length) {
      toast(fresh.length === 1 ? `New order #${fresh[0].code}` : `${fresh.length} new orders`, { type: "success" });
      if (soundWanted()) chime();
    }
  }

  /** After an action or a filter change: refresh now and report any error. */
  async function refresh() {
    try {
      await load();
    } catch (err) {
      failure(err);
    }
  }

  async function run(button, work) {
    setBusy(button, true);
    try {
      await work();
    } catch (err) {
      failure(err);
    } finally {
      if (button.isConnected) setBusy(button, false);
    }
  }

  const transition = (order, to_status, reason = "") =>
    api.post(`${base}/orders/${order.public_id}/transitions/`, { to_status, reason, expected_status: order.status });

  async function advance(order, to_status, message) {
    await transition(order, to_status);
    toast(message, { type: "success" });
    await refresh();
  }

  async function withReason(order, { title, description, label, submitLabel, request, done }) {
    const saved = await formDialog({
      title, description, submitLabel,
      fields: [{ name: "reason", label, type: "textarea", required: true, maxlength: 255 }],
      submit: (v) => request(v.reason),
    });
    if (saved) {
      toast(done, { type: "success" });
      await refresh();
    }
  }

  const reject = (order) => withReason(order, {
    title: `Reject order #${order.code}`, description: "The customer will see that the restaurant couldn't take this order.",
    label: "Reason", submitLabel: "Reject order", done: "Order rejected.",
    request: (reason) => transition(order, "REJECTED", reason),
  });

  const cancel = (order) => withReason(order, {
    title: `Cancel order #${order.code}`,
    description: order.status === "SERVING" ? "This order is already being served. Cancelling it can't be undone." : "Cancelling can't be undone.",
    label: "Reason", submitLabel: "Cancel order", done: "Order cancelled.",
    request: (reason) => api.post(`${base}/orders/${order.public_id}/cancel/`, {
      reason, expected_status: order.status, acknowledge_serving: order.status === "SERVING",
    }),
  });

  async function recordPayment(order) {
    const key = newKey(); // reused if the staff member retries from this dialog, so it can't be recorded twice
    const saved = await formDialog({
      title: `Record payment for #${order.code}`,
      description: `Record the ${formatMoney(order.total, order.currency)} you received. This is a note of payment you took, not an automatic check.`,
      submitLabel: "Record payment",
      fields: [
        { name: "method", label: "Paid by", type: "select", required: true, options: [{ value: "CASH", label: "Cash" }, { value: "TRANSFER", label: "Bank transfer" }] },
        { name: "reference", label: "Reference (optional)", type: "text", maxlength: 100, hint: "For example a transfer reference." },
      ],
      values: { method: "CASH" },
      submit: (v) => api.post(`${base}/orders/${order.public_id}/payment/`,
        { method: v.method, amount: order.total, reference: v.reference }, { headers: { "Idempotency-Key": key } }),
    });
    if (saved) {
      toast("Payment recorded.", { type: "success" });
      await refresh();
    }
  }

  async function showDetails(order) {
    const body = el("div", { class: "stack" }, el("div", { class: "skeleton skeleton--line", style: "height:1.5rem" }));
    const dialog = el("dialog", { class: "dialog", "aria-labelledby": "detail-title" },
      el("div", { class: "dialog__panel" },
        el("div", { class: "section-head", style: "margin:0" }, el("h2", { id: "detail-title" }, `Order #${order.code}`),
          el("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-label": "Close", onclick: () => dialog.close() }, icon("x"))),
        body));
    closeOnBackdrop(dialog);
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
    try {
      const d = await api.get(`${base}/orders/${order.public_id}/`);
      const when = (iso) => formatDateTime(iso, info.timezone);
      body.replaceChildren(
        el("div", { class: "row" },
          el("span", { class: "badge", "data-status": d.status }, STATUS_LABEL[d.status]),
          el("span", { class: "badge", "data-status": d.payment_status }, d.payment_status === "PAID" ? "Paid" : "Unpaid")),
        el("dl", { class: "details" },
          el("dt", {}, "Customer"), el("dd", {}, d.customer_name),
          el("dt", {}, "Phone"), el("dd", {}, el("a", { href: `tel:${d.customer_phone.replace(/[^\d+]/g, "")}` }, d.customer_phone)),
          el("dt", {}, "Ordering"), el("dd", {}, d.fulfilment_type === "DINE_IN" ? `Dine in${d.table_number ? `, table ${d.table_number}` : ""}` : "Pickup"),
          el("dt", {}, "Placed"), el("dd", {}, when(d.created_at)),
          d.notes ? el("dt", {}, "Notes") : null, d.notes ? el("dd", {}, d.notes) : null),
        el("ul", { class: "summary-lines" }, ...d.items.map((i) =>
          el("li", {}, el("span", {}, `${i.quantity} × ${i.item_name}`), el("span", { class: "price" }, formatMoney(i.line_total, d.currency))))),
        el("div", { class: "total-row" }, el("span", {}, "Total"), el("strong", { class: "price" }, formatMoney(d.total, d.currency))),
        el("h3", {}, "History"),
        el("ul", { class: "history" }, ...d.events.map((e) =>
          el("li", {}, el("strong", {}, STATUS_LABEL[e.to_status]), ` · ${ACTOR_LABEL[e.actor_type] ?? e.actor_type}${e.actor_email ? ` (${e.actor_email})` : ""} · ${when(e.created_at)}`,
            e.reason ? el("span", { class: "muted history__reason" }, ` “${e.reason}”`) : null))),
        d.payments.length ? el("h3", {}, "Payment") : null,
        ...d.payments.map((p) => el("p", {}, `${formatMoney(p.amount, p.currency)} by ${p.method === "CASH" ? "cash" : "bank transfer"}${p.reference ? ` (${p.reference})` : ""}, recorded by ${p.recorded_by_email}`)),
      );
    } catch (err) {
      dialog.close();
      failure(err);
    }
  }

  function actions(order) {
    const button = (label, cls, work, iconName) =>
      el("button", { class: `btn ${cls} btn--sm`, type: "button", onclick: (e) => run(e.currentTarget, work) }, iconName ? icon(iconName) : null, label);
    const list = [];
    if (order.status === "PENDING") {
      list.push(button("Confirm", "btn--primary", () => advance(order, "CONFIRMED", `Order #${order.code} confirmed.`), "check"));
      list.push(button("Reject", "btn--secondary", () => reject(order)));
    } else if (order.status === "CONFIRMED") {
      list.push(button("Start serving", "btn--primary", () => advance(order, "SERVING", `Order #${order.code} is being served.`)));
      list.push(button("Cancel", "btn--ghost", () => cancel(order)));
    } else if (order.status === "SERVING") {
      list.push(button("Mark served", "btn--primary", () => advance(order, "SERVED", `Order #${order.code} served.`), "check"));
      if (isManager) list.push(button("Cancel", "btn--ghost", () => cancel(order)));
    } else if (order.status === "SERVED" && order.payment_status === "UNPAID") {
      list.push(button("Record payment", "btn--primary", () => recordPayment(order)));
    }
    list.push(button("Details", "btn--ghost", () => showDetails(order)));
    return el("div", { class: "order-card__actions" }, ...list);
  }

  function card(order, isNew) {
    const where = order.fulfilment_type === "DINE_IN" ? (order.table_number ? `Dine in · Table ${order.table_number}` : "Dine in") : "Pickup";
    return el("article", { class: "card order-card", "data-status": order.status, "data-new": isNew ? "true" : null, "aria-labelledby": `o-${order.public_id}` },
      el("header", { class: "order-card__head" },
        el("h2", { id: `o-${order.public_id}`, class: "order-card__code" }, `#${order.code}`),
        el("span", { class: "badge", "data-status": order.status }, STATUS_LABEL[order.status]),
        order.status === "SERVED" ? el("span", { class: "badge", "data-status": order.payment_status }, order.payment_status === "PAID" ? "Paid" : "Unpaid") : null,
        el("span", { class: "muted order-card__time", title: formatDateTime(order.created_at, info.timezone) },
          `${formatClock(order.created_at, info.timezone)} · ${timeAgo(order.created_at)}`)),
      el("p", { class: "order-card__meta" }, `${where} · ${order.customer_name}`),
      el("ul", { class: "order-card__items" }, ...order.items.map((i) => el("li", {}, `${i.quantity} × ${i.item_name}`))),
      el("div", { class: "order-card__foot" }, el("strong", { class: "price" }, formatMoney(order.total, order.currency)), actions(order)),
    );
  }

  function render(newIds = new Set()) {
    const pending = orders.filter((o) => o.status === "PENDING").length;
    document.title = `${pending ? `(${pending}) ` : ""}Orders · ServeFlow`;
    const chips = el("div", { class: "chip-nav", style: "padding-inline:0", role: "group", "aria-label": "Show orders" },
      ...FILTERS.map((f) => el("button", {
        class: "chip", type: "button", "aria-current": String(f.id === filter.id),
        onclick: () => { filter = f; known = null; content.replaceChildren(skeleton()); refresh(); },
      }, f.label)));
    const more = el("button", { class: "btn btn--secondary", type: "button", hidden: !nextQuery }, "Load more");
    more.addEventListener("click", () => run(more, async () => {
      const page = await api.get(`${base}/orders/${nextQuery}`);
      orders = [...orders, ...page.results];
      loadedMore = true;
      nextQuery = page.next ? new URL(page.next, location.href).search : null;
      render();
    }));
    content.replaceChildren(
      chips,
      orders.length
        ? el("div", { class: "order-list" }, ...orders.map((o) => card(o, newIds.has(o.public_id))))
        : emptyState({ iconName: "list", title: filter.empty, text: "New orders appear here by themselves." }),
      more,
    );
  }

  const skeleton = () =>
    el("div", { class: "card card__pad stack", "aria-hidden": "true" },
      ...[60, 85, 70].map((w) => el("div", { class: "skeleton skeleton--line", style: `width:${w}%;height:1.25rem` })));

  content.replaceChildren(skeleton());
  try {
    info = await api.get(`${base}/`);
  } catch (err) {
    failure(err);
  }
  await refresh();

  // Live: look for new and changed orders every 5 seconds.
  const badge = liveBadge();
  attachBadge(badge);
  const sound = el("button", { class: "btn btn--secondary btn--sm sound-toggle", type: "button", "aria-pressed": String(soundWanted()) },
    "Sound: ", el("span", {}, soundWanted() ? "on" : "off"));
  sound.addEventListener("click", () => {
    const on = !soundWanted();
    try { localStorage.setItem(SOUND_STORAGE_KEY, on ? "on" : "off"); } catch { /* ignore */ }
    if (on) {
      audio ??= new (window.AudioContext ?? window.webkitAudioContext)();
      audio.resume?.();
      chime();
    }
    sound.setAttribute("aria-pressed", String(on));
    sound.lastChild.textContent = on ? "on" : "off";
  });
  if (soundWanted()) {
    // Browsers only allow sound after a click, so a saved "on" starts at the next click anywhere.
    document.addEventListener("click", () => { audio ??= new (window.AudioContext ?? window.webkitAudioContext)(); }, { once: true });
  }
  document.querySelector(".page-head").append(sound);
  sound.style.marginTop = "var(--s-2)";
  sound.style.justifySelf = "start";

  startLive({
    badge,
    intervalMs: 5000,
    shouldSkip: () => loadedMore || defaultShouldSkip(),
    refresh: async () => {
      try {
        await load({ announce: true });
      } catch (err) {
        if (handleSessionExpiry(err, HREF)) return;
        throw err;
      }
    },
  });
}

main();
