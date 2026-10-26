/* Shared UI helpers: icons, toasts, confirm dialog, busy buttons, money formatting.
   Uses textContent everywhere; never inserts API data as HTML. */

const SVG_NS = "http://www.w3.org/2000/svg";
const SPRITE = new URL("../assets/icons.svg", import.meta.url).href;

export function icon(name, { large = false } = {}) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", large ? "icon icon--lg" : "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `${SPRITE}#i-${name}`);
  svg.append(use);
  return svg;
}

/* ---------- DOM helpers (text only: strings are always text nodes, never HTML) ---------- */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  node.append(...children);
  return node;
}

export function emptyState({ iconName = "list", title, text, action } = {}) {
  const box = el("div", { class: "card empty" },
    el("span", { class: "empty__icon" }, icon(iconName, { large: true })),
    el("h2", {}, title),
  );
  if (text) box.append(el("p", {}, text));
  if (action) box.append(action);
  return box;
}

/* ---------- Money (display only; the backend is authoritative for totals) ---------- */
export function formatMoney(amount, currency, locale) {
  const n = typeof amount === "number" ? amount : Number.parseFloat(amount);
  if (!Number.isFinite(n)) return "";
  try {
    return new Intl.NumberFormat(locale || undefined, { style: "currency", currency }).format(n);
  } catch {
    return `${n.toFixed(2)} ${currency ?? ""}`.trim();
  }
}

/* ---------- Busy buttons ---------- */
export function setBusy(button, busy) {
  button.toggleAttribute("aria-busy", busy);
  if (busy) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
  button.disabled = busy;
}

/* ---------- Toasts ---------- */
const TOAST_ICON = { success: "check", error: "alert", info: "info" };
const MAX_TOASTS = 3;
let region;

function toastRegion() {
  if (!region) {
    region = document.createElement("div");
    region.className = "toasts";
    region.setAttribute("aria-live", "polite");
    document.body.append(region);
  }
  return region;
}

export function toast(message, { type = "info", duration } = {}) {
  const host = toastRegion();
  while (host.children.length >= MAX_TOASTS) host.firstElementChild.remove();

  const el = document.createElement("div");
  el.className = `toast toast--${type}`;
  el.setAttribute("role", type === "error" ? "alert" : "status");

  const msg = document.createElement("span");
  msg.className = "toast__msg";
  msg.textContent = message;

  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast__close";
  close.setAttribute("aria-label", "Dismiss notification");
  close.append(icon("x"));

  el.append(icon(TOAST_ICON[type] ?? "info"), msg, close);
  host.append(el);

  let timer;
  const dismiss = () => {
    clearTimeout(timer);
    el.dataset.leaving = "true";
    setTimeout(() => el.remove(), 220);
  };
  const arm = () => {
    clearTimeout(timer);
    timer = setTimeout(dismiss, duration ?? (type === "error" ? 8000 : 4000));
  };
  close.addEventListener("click", dismiss);
  el.addEventListener("pointerenter", () => clearTimeout(timer));
  el.addEventListener("pointerleave", arm);
  el.addEventListener("focusin", () => clearTimeout(timer));
  el.addEventListener("focusout", arm);
  arm();
  return dismiss;
}

/* ---------- Dialogs ---------- */
/* Clicking the backdrop (the <dialog> itself, outside .dialog__panel) closes it. */
export function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close("cancel");
  });
}

let dialogCounter = 0;

export function confirmDialog({ title, message, confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false }) {
  return new Promise((resolve) => {
    const id = `confirm-${++dialogCounter}`;
    const dialog = document.createElement("dialog");
    dialog.className = "dialog";
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    dialog.setAttribute("aria-describedby", `${id}-desc`);

    const form = document.createElement("form");
    form.method = "dialog";
    form.className = "dialog__panel";

    const h = document.createElement("h2");
    h.id = `${id}-title`;
    h.textContent = title;
    const p = document.createElement("p");
    p.id = `${id}-desc`;
    p.className = "muted";
    p.textContent = message;

    const footer = document.createElement("div");
    footer.className = "dialog__footer";
    const cancel = document.createElement("button");
    cancel.className = "btn btn--secondary";
    cancel.value = "cancel";
    cancel.textContent = cancelLabel;
    const ok = document.createElement("button");
    ok.className = `btn ${danger ? "btn--danger" : "btn--primary"}`;
    ok.value = "confirm";
    ok.textContent = confirmLabel;
    footer.append(cancel, ok);

    form.append(h, p, footer);
    dialog.append(form);
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "confirm");
      dialog.remove();
    });
    closeOnBackdrop(dialog);
    document.body.append(dialog);
    dialog.showModal();
    // Consequential actions start focused on the safe choice.
    (danger ? cancel : ok).focus();
  });
}
