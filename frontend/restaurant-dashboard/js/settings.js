import { ApiError, api } from "../../shared/js/api.js";
import { el, emptyState, icon, toast } from "../../shared/js/ui.js";
import { formDialog } from "./form-dialog.js";
import { fulfilmentErrors, restaurantFields } from "./regional.js";
import { hasRole } from "./session.js";
import { bootDashboard, handleSessionExpiry } from "./shell.js";

const HREF = "settings.html";
const content = document.getElementById("content");

const skeleton = () =>
  el("div", { class: "card card__pad stack", "aria-hidden": "true" },
    ...[60, 85, 70].map((w) => el("div", { class: "skeleton skeleton--line", style: `width:${w}%;height:1.25rem` })));

const fulfilmentText = (r) => {
  const parts = [];
  if (r.pickup_enabled) parts.push("Pickup");
  if (r.dine_in_enabled) parts.push(r.requires_table_number ? "Dine in (table number required)" : "Dine in");
  return parts.join(", ");
};

async function main() {
  const ctx = await bootDashboard({ href: HREF });
  if (!ctx) return;
  const canEdit = hasRole(ctx.role, "MANAGER");
  const url = `/restaurants/${encodeURIComponent(ctx.restaurant.slug)}/settings/`;
  const customerUrl = new URL(`../customer/index.html?r=${encodeURIComponent(ctx.restaurant.slug)}`, location.href).href;
  let data;

  const failure = (err) => {
    if (handleSessionExpiry(err, HREF)) return;
    toast(err instanceof ApiError ? err.message : "Something went wrong.", { type: "error" });
  };

  async function load() {
    content.replaceChildren(skeleton());
    try {
      data = await api.get(url);
      render();
    } catch (err) {
      if (handleSessionExpiry(err, HREF)) return;
      content.replaceChildren(emptyState({
        iconName: "alert", title: "Couldn't load settings",
        text: err instanceof ApiError ? err.message : "Something went wrong.",
        action: el("button", { class: "btn btn--secondary", type: "button", onclick: load }, icon("refresh"), "Try again"),
      }));
    }
  }

  async function edit() {
    const fields = restaurantFields({ timezone: data.timezone });
    const saved = await formDialog({
      title: "Edit restaurant details", fields, values: data, validateForm: fulfilmentErrors,
      submit: (v) => api.patch(url, v),
    });
    if (saved) {
      toast("Settings saved.", { type: "success" });
      await load();
    }
  }

  function ordersCard() {
    const state = el("span", { class: "muted" }, data.accepting_orders ? "On" : "Off");
    const toggle = el("button", {
      class: "switch", type: "button", role: "switch", "aria-checked": String(data.accepting_orders),
      "aria-label": "Accepting orders",
    });
    toggle.addEventListener("click", async () => {
      toggle.disabled = true;
      try {
        data = await api.patch(url, { accepting_orders: !data.accepting_orders });
        toggle.setAttribute("aria-checked", String(data.accepting_orders));
        state.textContent = data.accepting_orders ? "On" : "Off";
        toast(data.accepting_orders ? "Orders switched on." : "Orders paused.", { type: "success" });
      } catch (err) {
        failure(err);
      } finally {
        toggle.disabled = false;
      }
    });
    return el("section", { class: "card card__pad stack", "aria-labelledby": "orders-h" },
      el("div", { class: "section-head", style: "margin:0" },
        el("h2", { id: "orders-h" }, "Accepting orders"),
        el("div", { class: "row" }, state, toggle)),
      el("p", { class: "muted" }, "Switch this off during a rush to pause new orders. Customers can still see your menu, and orders already placed are not affected. New restaurants start with orders off."),
    );
  }

  function detailsCard() {
    const details = el("dl", { class: "details" },
      el("dt", {}, "Name"), el("dd", {}, data.name),
      el("dt", {}, "Web address"), el("dd", {}, data.slug),
      el("dt", {}, "Currency"), el("dd", {}, data.currency),
      el("dt", {}, "Timezone"), el("dd", {}, data.timezone),
      el("dt", {}, "Ordering options"), el("dd", {}, fulfilmentText(data)),
      el("dt", {}, "Address"), el("dd", {}, data.address || "Not set"),
      el("dt", {}, "Phone"), el("dd", {}, data.contact_phone || "Not set"),
      el("dt", {}, "About"), el("dd", {}, data.description || "Not set"),
    );
    return el("section", { class: "card card__pad stack", "aria-labelledby": "details-h" },
      el("div", { class: "section-head", style: "margin:0" },
        el("h2", { id: "details-h" }, "Restaurant details"),
        canEdit ? el("button", { class: "btn btn--secondary btn--sm", type: "button", onclick: edit }, "Edit") : null),
      details,
      canEdit ? null : el("p", { class: "muted" }, "Managers and owners can edit these details."),
    );
  }

  function linkCard() {
    const copy = el("button", { class: "btn btn--secondary btn--sm", type: "button" }, "Copy");
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(customerUrl);
        toast("Link copied.", { type: "success" });
      } catch {
        toast("Couldn't copy. Select the link and copy it.", { type: "error" });
      }
    });
    return el("section", { class: "card card__pad stack", "aria-labelledby": "link-h" },
      el("h2", { id: "link-h" }, "Your customer link"),
      el("p", { class: "muted" }, "Share this link or turn it into a QR code. Customers can browse your menu from it."),
      el("p", { class: "copy-row" }, el("code", { class: "copy-row__url" }, customerUrl)),
      el("div", { class: "row" }, copy,
        el("a", { class: "btn btn--secondary btn--sm", href: customerUrl, target: "_blank", rel: "noopener" }, "Open")),
    );
  }

  function render() {
    content.replaceChildren(ordersCard(), detailsCard(), linkCard());
  }

  await load();
}

main();
