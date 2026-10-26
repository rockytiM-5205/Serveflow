import { ApiError, api } from "../../shared/js/api.js";
import { buildForm } from "../../shared/js/form-builder.js";
import { el, emptyState, formatMoney, icon, toast } from "../../shared/js/ui.js";
import { clearIdempotencyKey, createCart, describeCart, fromCents, idempotencyKeyFor, saveLastOrder } from "./cart.js";
import { bootCustomer, show } from "./restaurant.js";

const ORDER_ERRORS = {
  item_unavailable: "Some items are no longer available, so we removed them from your order. Please check it and try again.",
  throttled: "Too many attempts. Please wait a minute and try again.",
  network_error: "We couldn't reach the server, so your order has not been placed. Check your connection and press Place order again. Retrying never creates a duplicate.",
  timeout: "The server took too long, so your order may not have been placed. Press Place order again. Retrying never creates a duplicate.",
};

async function main() {
  const ctx = await bootCustomer();
  if (!ctx) return;
  const { slug, restaurant } = ctx;
  const menuUrl = `menu.html?r=${encodeURIComponent(slug)}`;
  document.getElementById("back-link").href = menuUrl;
  const back = (label) => el("a", { class: "btn btn--secondary", href: menuUrl }, label);

  if (!restaurant.accepting_orders) {
    show(emptyState({
      iconName: "clock", title: "Not taking orders right now",
      text: "This restaurant has paused orders. Please try again in a little while.", action: back("Back to the menu"),
    }));
    return;
  }

  let menu;
  try {
    menu = await api.get(`/restaurants/${encodeURIComponent(slug)}/menu/`);
  } catch (err) {
    show(emptyState({
      iconName: "alert", title: "Couldn't load your order", text: err instanceof ApiError ? err.message : "Something went wrong.",
      action: el("button", { class: "btn btn--secondary", type: "button", onclick: () => location.reload() }, icon("refresh"), "Try again"),
    }));
    return;
  }
  const currency = menu.restaurant.currency;
  const itemsById = new Map(menu.categories.flatMap((c) => c.items).map((item) => [item.id, item]));
  const cart = createCart(slug);
  const removed = cart.reconcile(itemsById);

  const summary = el("section", { class: "card card__pad stack", "aria-labelledby": "summary-h" });
  const renderSummary = () => {
    const { lines, totalCents } = describeCart(cart, itemsById);
    summary.replaceChildren(
      el("div", { class: "section-head", style: "margin:0" }, el("h2", { id: "summary-h" }, "Your order"),
        el("a", { href: menuUrl }, "Edit")),
      el("ul", { class: "summary-lines" }, ...lines.map(({ item, quantity, lineCents }) =>
        el("li", {}, el("span", {}, `${quantity} × ${item.name}`), el("span", { class: "price" }, formatMoney(fromCents(lineCents), currency))))),
      el("div", { class: "total-row" }, el("span", {}, "Estimated total"), el("strong", { class: "price" }, formatMoney(fromCents(totalCents), currency))),
      el("p", { class: "muted", style: "font-size:var(--fs-sm)" }, "The restaurant works out the final total when you place the order."),
    );
  };

  if (cart.count() === 0) {
    show(emptyState({
      iconName: "bag", title: "Your order is empty", text: removed.length ? "The items you chose aren't available any more." : "Add something from the menu first.",
      action: back("Browse the menu"),
    }));
    return;
  }
  if (removed.length) toast("Some items aren't available any more, so we removed them.", { type: "info" });
  renderSummary();

  const options = [];
  if (restaurant.pickup_enabled) options.push({ value: "PICKUP", label: "Pickup", hint: "Collect it when it's ready", icon: "bag" });
  if (restaurant.dine_in_enabled) options.push({ value: "DINE_IN", label: "Dine in", hint: "Served at your table", icon: "utensils" });
  const onlyType = options.length === 1 ? options[0].value : null;

  const fields = [];
  if (!onlyType) fields.push({ name: "fulfilment_type", label: "How would you like it?", type: "radio", required: true, options });
  fields.push(
    { name: "customer_name", label: "Your name", type: "text", required: true, maxlength: 80, autocomplete: "name" },
    {
      name: "customer_phone", label: "Phone number", type: "tel", required: true, maxlength: 30, inputmode: "tel", autocomplete: "tel",
      hint: "The restaurant may call you about your order.",
      validate: (v) => (/^[0-9]{7,15}$/.test(v.replace(/[\s().+-]/g, "")) ? null : "Enter a valid phone number."),
    },
    { name: "table_number", label: restaurant.requires_table_number ? "Table number" : "Table number (optional)", type: "text", maxlength: 20, inputmode: "text" },
    { name: "notes", label: "Notes for the restaurant (optional)", type: "textarea", maxlength: 500 },
  );

  const { form, controls } = buildForm({
    idPrefix: "co",
    fields,
    values: { fulfilment_type: options[0].value },
    submitLabel: "Place order",
    validateForm: (values) => {
      const type = values.fulfilment_type || onlyType;
      return type === "DINE_IN" && restaurant.requires_table_number && !values.table_number ? { table_number: "Enter your table number." } : {};
    },
    submit: async (values) => {
      const type = values.fulfilment_type || onlyType;
      const payload = {
        customer_name: values.customer_name,
        customer_phone: values.customer_phone,
        fulfilment_type: type,
        table_number: type === "DINE_IN" && values.table_number ? values.table_number : null,
        notes: values.notes,
        items: cart.entries().map(([id, quantity]) => ({ menu_item_id: id, quantity })),
      };
      // The same order retried reuses its key, so a dropped connection can never place it twice.
      const key = idempotencyKeyFor(slug, payload);
      try {
        return await api.post(`/restaurants/${encodeURIComponent(slug)}/orders/`, payload, { headers: { "Idempotency-Key": key } });
      } catch (err) {
        if (!(err instanceof ApiError)) throw err;
        if (err.code === "item_unavailable") {
          cart.remove((err.details?.items ?? []).map((problem) => problem.id));
          if (cart.count() === 0) location.reload();
          else renderSummary();
        }
        const friendly = ORDER_ERRORS[err.code] ?? (err.status === 429 ? ORDER_ERRORS.throttled : null);
        throw friendly ? new ApiError({ status: err.status, code: err.code, message: friendly, details: err.details }) : err;
      }
    },
    onSuccess: (order) => {
      saveLastOrder(slug, order.token);
      cart.clear();
      clearIdempotencyKey(slug);
      location.replace(`order.html?r=${encodeURIComponent(slug)}#${order.token}`);
    },
  });

  const tableWrap = controls.get("table_number").wrap;
  const typeControl = controls.get("fulfilment_type");
  const currentType = () => typeControl?.radios.find((r) => r.checked)?.value ?? onlyType;
  const syncTable = () => { tableWrap.hidden = currentType() !== "DINE_IN"; };
  typeControl?.radios.forEach((radio) => radio.addEventListener("change", syncTable));
  syncTable();

  show(el("div", { class: "checkout" }, summary, el("section", { class: "card card__pad stack", "aria-labelledby": "details-h" },
    el("h2", { id: "details-h" }, "Your details"), form)));
}

main();
