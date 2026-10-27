import { ApiError, api } from "../../shared/js/api.js";
import { confirmDialog, el, emptyState, formatMoney, icon, toast } from "../../shared/js/ui.js";
import { isHttpsUrl, isValidPrice, isValidSortOrder } from "../../shared/js/validators.js";
import { attachBadge, liveBadge, startLive } from "../../shared/js/live.js";
import { formDialog } from "./form-dialog.js";
import { hasRole } from "./session.js";
import { bootDashboard, handleSessionExpiry } from "./shell.js";

const HREF = "menu.html";
const content = document.getElementById("content");

const skeleton = () =>
  el("div", { class: "card card__pad stack", "aria-hidden": "true" },
    ...[60, 85, 70].map((w) => el("div", { class: "skeleton skeleton--line", style: `width:${w}%;height:1.25rem` })));

const categoryFields = [
  { name: "name", label: "Name", type: "text", required: true, maxlength: 80 },
  { name: "description", label: "Description (optional)", type: "text", maxlength: 255 },
  {
    name: "sort_order", label: "Order on the menu", type: "text", inputmode: "numeric", cast: "number", required: true,
    hint: "Lower numbers appear first.",
    validate: (v) => (isValidSortOrder(v) ? null : "Enter a whole number from 0 to 32767."),
  },
  { name: "is_active", label: "Visible to customers", type: "checkbox" },
];

function itemFields(categories) {
  return [
    {
      name: "category", label: "Category", type: "select", required: true, cast: "number",
      options: categories.map((c) => ({ value: c.id, label: c.name })),
    },
    { name: "name", label: "Name", type: "text", required: true, maxlength: 120 },
    { name: "description", label: "Description (optional)", type: "textarea", maxlength: 500 },
    {
      name: "price", label: "Price", type: "text", required: true, inputmode: "decimal", hint: "For one unit, e.g. 2.50",
      validate: (v) => (isValidPrice(v) ? null : "Enter an amount like 5 or 2.50."),
    },
    {
      name: "unit_name", label: "Sold per", type: "text", required: true, maxlength: 32,
      hint: "What one unit is: spoon, piece, portion, plate…",
    },
    {
      name: "image_url", label: "Photo link (optional)", type: "text", maxlength: 500, hint: "A link starting with https://",
      validate: (v) => (isHttpsUrl(v) ? null : "Use a link that starts with https://"),
    },
    { name: "is_available", label: "Available now", type: "checkbox" },
  ];
}

async function main() {
  const ctx = await bootDashboard({ href: HREF });
  if (!ctx) return;
  const canEdit = hasRole(ctx.role, "MANAGER");
  const base = `/restaurants/${encodeURIComponent(ctx.restaurant.slug)}`;
  let currency = "USD";
  let showArchived = false;
  let categories = [];
  let items = [];

  const failure = (err) => {
    if (handleSessionExpiry(err, HREF)) return;
    toast(err instanceof ApiError ? err.message : "Something went wrong.", { type: "error" });
  };

  async function fetchAll() {
    const [restaurant, cats, its] = await Promise.all([
      api.get(`${base}/`),
      api.get(`${base}/menu/categories/`),
      api.get(`${base}/menu/items/${showArchived ? "?include_archived=1" : ""}`),
    ]);
    return { currency: restaurant.currency, categories: cats, items: its };
  }

  let lastSignature = "";
  function apply(data) {
    ({ currency, categories, items } = data);
    lastSignature = JSON.stringify(data);
    render();
  }

  async function load() {
    content.replaceChildren(skeleton());
    try {
      apply(await fetchAll());
    } catch (err) {
      if (handleSessionExpiry(err, HREF)) return;
      const forbidden = err instanceof ApiError && err.status === 403;
      content.replaceChildren(emptyState({
        iconName: forbidden ? "lock" : "alert",
        title: forbidden ? "You don't have access to this page" : "Couldn't load the menu",
        text: err instanceof ApiError ? err.message : "Something went wrong.",
        action: forbidden ? null : el("button", { class: "btn btn--secondary", type: "button", onclick: load }, icon("refresh"), "Try again"),
      }));
    }
  }

  async function saveAndReload(done, request) {
    const saved = await request();
    if (saved) {
      toast(done, { type: "success" });
      await load();
    }
  }

  const newCategory = () => saveAndReload("Category created.", () => formDialog({
    title: "New category", fields: categoryFields, submitLabel: "Create category",
    values: { sort_order: categories.length ? Math.max(...categories.map((c) => c.sort_order)) + 1 : 0, is_active: true },
    submit: (v) => api.post(`${base}/menu/categories/`, v),
  }));

  const editCategory = (category) => saveAndReload("Category saved.", () => formDialog({
    title: "Edit category", fields: categoryFields, values: category,
    submit: (v) => api.patch(`${base}/menu/categories/${category.id}/`, v),
  }));

  const toPayload = (v) => ({ ...v, image_url: v.image_url || null });

  const newItem = () => saveAndReload("Item created.", () => formDialog({
    title: "New item", fields: itemFields(categories), submitLabel: "Create item",
    values: { unit_name: "portion", is_available: true },
    submit: (v) => api.post(`${base}/menu/items/`, toPayload(v)),
  }));

  const editItem = (item) => saveAndReload("Item saved.", () => formDialog({
    title: "Edit item", fields: itemFields(categories), values: item,
    submit: (v) => api.patch(`${base}/menu/items/${item.id}/`, toPayload(v)),
  }));

  async function archiveItem(item) {
    const ok = await confirmDialog({
      title: `Archive ${item.name}?`,
      message: "Customers will no longer see it. Past orders keep their record of it.",
      confirmLabel: "Archive", danger: true,
    });
    if (!ok) return;
    try {
      await api.post(`${base}/menu/items/${item.id}/archive/`);
      toast("Item archived.", { type: "success" });
      await load();
    } catch (err) {
      failure(err);
    }
  }

  function itemRow(item) {
    const state = el("span", { class: "muted item-row__state" }, item.is_available ? "Available" : "Unavailable");
    const toggle = el("button", {
      class: "switch", type: "button", role: "switch", "aria-checked": String(item.is_available),
      "aria-label": `${item.name} is available`, disabled: item.archived,
    });
    toggle.addEventListener("click", async () => {
      toggle.disabled = true;
      try {
        const updated = await api.patch(`${base}/menu/items/${item.id}/availability/`, { is_available: !item.is_available });
        Object.assign(item, updated);
        toggle.setAttribute("aria-checked", String(item.is_available));
        state.textContent = item.is_available ? "Available" : "Unavailable";
      } catch (err) {
        failure(err);
      } finally {
        toggle.disabled = false;
      }
    });

    const actions = el("div", { class: "item-row__actions" }, state, toggle);
    if (canEdit && !item.archived) {
      actions.append(
        el("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-label": `Edit ${item.name}`, onclick: () => editItem(item) }, "Edit"),
        el("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-label": `Archive ${item.name}`, onclick: () => archiveItem(item) }, icon("trash")),
      );
    }
    return el("li", { class: "item-row" },
      el("div", { class: "item-row__main" },
        el("span", { class: "member-name" }, item.name, item.archived ? el("span", { class: "badge", "data-status": "CANCELLED" }, "Archived") : null),
        el("span", { class: "muted member-email" }, `${formatMoney(item.price, currency)} / ${item.unit_name}`),
      ),
      actions,
    );
  }

  function render() {
    const archivedToggle = el("input", { type: "checkbox", id: "show-archived", checked: showArchived });
    archivedToggle.addEventListener("change", () => {
      showArchived = archivedToggle.checked;
      load();
    });
    const toolbar = el("div", { class: "toolbar" },
      canEdit ? el("button", { class: "btn btn--primary", type: "button", onclick: newItem, disabled: categories.length === 0 }, icon("plus"), "New item") : null,
      canEdit ? el("button", { class: "btn btn--secondary", type: "button", onclick: newCategory }, icon("plus"), "New category") : null,
      canEdit ? el("label", { class: "check", for: "show-archived" }, archivedToggle, "Show archived") : null,
    );
    const nodes = [toolbar];
    if (!canEdit) {
      nodes.push(el("p", { class: "muted" }, "You can mark items available or unavailable. Managers and owners can change the menu."));
    }

    if (categories.length === 0) {
      nodes.push(emptyState({
        iconName: "book",
        title: "No menu yet",
        text: canEdit ? "Start with a category, then add your items." : "A manager or owner needs to create the menu.",
        action: canEdit ? el("button", { class: "btn btn--primary", type: "button", onclick: newCategory }, icon("plus"), "Create a category") : null,
      }));
    }

    for (const category of categories) {
      const mine = items.filter((item) => item.category === category.id);
      nodes.push(el("section", { class: "card cat-card", "aria-labelledby": `cat-${category.id}` },
        el("header", { class: "cat-card__head" },
          el("h2", { id: `cat-${category.id}` }, category.name,
            category.is_active ? null : el("span", { class: "badge", "data-status": "INACTIVE" }, "Hidden from customers")),
          canEdit ? el("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-label": `Edit category ${category.name}`, onclick: () => editCategory(category) }, "Edit") : null,
        ),
        mine.length
          ? el("ul", { class: "item-list" }, ...mine.map(itemRow))
          : el("p", { class: "muted cat-card__empty" }, "No items yet."),
      ));
    }
    content.replaceChildren(...nodes);
  }

  await load();

  // Live: pick up changes other staff make (availability, new items) every 10 seconds.
  const badge = liveBadge();
  attachBadge(badge);
  startLive({
    badge,
    intervalMs: 10000,
    shouldSkip: () => Boolean(document.querySelector('dialog[open], [aria-busy="true"], .switch:disabled')),
    refresh: async () => {
      try {
        const data = await fetchAll();
        if (JSON.stringify(data) !== lastSignature) apply(data);
      } catch (err) {
        if (handleSessionExpiry(err, HREF)) return;
        throw err;
      }
    },
  });
}

main();
