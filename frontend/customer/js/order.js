import { ApiError, api } from "../../shared/js/api.js";
import { confirmDialog, el, emptyState, formatMoney, icon, toast } from "../../shared/js/ui.js";
import { loadLastOrder } from "./cart.js";
import { DETAIL, HEADLINE, isTerminal, timelineSteps, tokenFromHash } from "./order-view.js";
import { parseSlug } from "./helpers.js";

const content = document.getElementById("content");
const live = document.getElementById("live");
const POLL_MS = 10000;

const slugParam = parseSlug(location.search);
const token = tokenFromHash(location.hash) ?? (slugParam ? loadLastOrder(slugParam) : null);

const show = (node) => content.replaceChildren(node);
const notFound = () => show(emptyState({
  iconName: "list", title: "We can't find this order",
  text: "The link may be incomplete or no longer valid. Check it with the restaurant.",
  action: slugParam ? el("a", { class: "btn btn--secondary", href: `menu.html?r=${encodeURIComponent(slugParam)}` }, "Back to the menu") : null,
}));

let timer = null;
let lastJson = "";
let lastStatus = null;

function render(order) {
  const menuUrl = `menu.html?r=${encodeURIComponent(order.restaurant.slug)}`;
  document.getElementById("brand-name").textContent = order.restaurant.name;
  document.getElementById("brand-link").href = menuUrl;
  document.title = `Order #${order.code} · ${order.restaurant.name}`;

  const where = order.fulfilment_type === "DINE_IN" ? (order.table_number ? `Dine in · Table ${order.table_number}` : "Dine in") : "Pickup";
  const header = el("section", { class: "card card__pad stack", "aria-labelledby": "order-code" },
    el("p", { class: "eyebrow" }, "Your order"),
    el("h1", { id: "order-code", class: "order-code" }, `#${order.code}`),
    el("h2", { class: "order-headline" }, HEADLINE[order.status] ?? order.status),
    DETAIL[order.status] ? el("p", { class: "muted" }, DETAIL[order.status]) : null,
    el("div", { class: "row" },
      el("span", { class: "badge", "data-status": order.status }, order.status === "SERVING" ? "Being served" : order.status.charAt(0) + order.status.slice(1).toLowerCase()),
      el("span", { class: "badge", "data-status": order.payment_status }, order.payment_status === "PAID" ? "Paid" : "Not paid yet"),
      el("span", { class: "muted" }, where)),
  );

  const steps = el("ol", { class: "timeline", "aria-label": "Order progress" }, ...timelineSteps(order).map((step) =>
    el("li", { class: "timeline__step", "data-done": String(step.done), "data-current": String(step.current), "aria-current": step.current ? "step" : null },
      el("span", { class: "timeline__label" }, step.label))));

  const items = el("section", { class: "card card__pad stack", "aria-labelledby": "items-h" },
    el("h2", { id: "items-h" }, "What you ordered"),
    el("ul", { class: "summary-lines" }, ...order.items.map((item) =>
      el("li", {}, el("span", {}, `${item.quantity} × ${item.name}`), el("span", { class: "price" }, formatMoney(item.line_total, order.currency))))),
    el("div", { class: "total-row" }, el("span", {}, "Total"), el("strong", { class: "price" }, formatMoney(order.total, order.currency))),
    order.status === "SERVED" && order.payment_status === "UNPAID"
      ? el("p", { class: "muted" }, "Pay the restaurant when you're ready.") : null,
  );

  const actions = el("div", { class: "row" });
  if (order.cancellable) {
    actions.append(el("button", { class: "btn btn--secondary", type: "button", onclick: cancelOrder }, "Cancel order"));
  }
  actions.append(el("a", { class: "btn btn--ghost", href: menuUrl }, "Back to the menu"));

  show(el("div", { class: "stack" }, header, el("section", { class: "card card__pad" }, steps), items, actions));
}

async function cancelOrder() {
  const ok = await confirmDialog({
    title: "Cancel this order?", message: "The restaurant hasn't confirmed it yet, so you can still cancel.",
    confirmLabel: "Cancel order", cancelLabel: "Keep order", danger: true,
  });
  if (!ok) return;
  try {
    const order = await api.post(`/orders/${token}/cancel/`);
    toast("Order cancelled.", { type: "success" });
    apply(order);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      toast("It's too late to cancel: the restaurant has already responded.", { type: "info" });
      await poll();
    } else {
      toast(err instanceof ApiError ? err.message : "Couldn't cancel. Try again.", { type: "error" });
    }
  }
}

function apply(order) {
  const json = JSON.stringify(order);
  if (json !== lastJson) {
    lastJson = json;
    render(order);
    if (lastStatus !== null && lastStatus !== order.status) live.textContent = HEADLINE[order.status] ?? "";
    lastStatus = order.status;
  }
  if (isTerminal(order.status)) stop();
}

function stop() {
  clearInterval(timer);
  timer = null;
}

async function poll() {
  if (document.hidden) return;
  try {
    apply(await api.get(`/orders/${token}/`));
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      stop();
      notFound();
    } // otherwise keep showing the last known state and try again next time
  }
}

async function main() {
  if (!token) {
    notFound();
    return;
  }
  try {
    apply(await api.get(`/orders/${token}/`));
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return notFound();
    show(emptyState({
      iconName: "alert", title: "Couldn't load your order", text: err instanceof ApiError ? err.message : "Something went wrong.",
      action: el("button", { class: "btn btn--secondary", type: "button", onclick: () => location.reload() }, icon("refresh"), "Try again"),
    }));
    return;
  }
  if (!isTerminal(lastStatus)) {
    timer = setInterval(poll, POLL_MS);
    document.addEventListener("visibilitychange", () => { if (!document.hidden && timer) poll(); });
  }
}

main();
