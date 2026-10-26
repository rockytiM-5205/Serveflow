import { toast, confirmDialog, setBusy, formatMoney, closeOnBackdrop, icon } from "./ui.js";

/* Sample prices are formatted the same way real ones will be. */
document.querySelectorAll("[data-money]").forEach((el) => {
  el.textContent = formatMoney(el.dataset.money, el.dataset.currency);
});

/* ---------- Food card: Add button <-> quantity stepper ---------- */
const MAX_QTY = 99;

function iconButton(label, name) {
  const b = document.createElement("button");
  b.type = "button";
  b.setAttribute("aria-label", label);
  b.append(icon(name));
  return b;
}

function renderActions(card, qty, focus) {
  const box = card.querySelector(".food-card__actions");
  const name = card.querySelector(".food-card__name").textContent;
  card.dataset.selected = qty > 0 ? "true" : "false";
  box.replaceChildren();

  if (qty === 0) {
    const add = document.createElement("button");
    add.type = "button";
    add.className = "btn btn--primary btn--block";
    add.append(icon("plus"), document.createTextNode("Add"));
    add.setAttribute("aria-label", `Add ${name}`);
    add.addEventListener("click", () => renderActions(card, 1, "plus"));
    box.append(add);
    if (focus === "add") add.focus();
    return;
  }

  const group = document.createElement("div");
  group.className = "stepper";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", `Quantity of ${name}`);
  const minus = iconButton(`Remove one ${name}`, "minus");
  const plus = iconButton(`Add one ${name}`, "plus");
  plus.disabled = qty >= MAX_QTY;
  const out = document.createElement("output");
  out.textContent = String(qty);
  minus.addEventListener("click", () => renderActions(card, qty - 1, qty - 1 > 0 ? "minus" : "add"));
  plus.addEventListener("click", () => renderActions(card, qty + 1, "plus"));
  group.append(minus, out, plus);
  box.append(group);
  if (focus === "plus") plus.focus();
  if (focus === "minus") minus.focus();
}

document.querySelectorAll(".food-card[data-sample]").forEach((card) => {
  if (card.dataset.unavailable === "true") return;
  renderActions(card, Number(card.dataset.qty || 0));
});

/* ---------- Category chips and sheet ---------- */
const chips = document.querySelectorAll("#category-chips .chip");
chips.forEach((chip) =>
  chip.addEventListener("click", () => {
    chips.forEach((c) => c.setAttribute("aria-current", String(c === chip)));
  }),
);

const sheet = document.getElementById("category-sheet");
closeOnBackdrop(sheet);
document.getElementById("open-sheet").addEventListener("click", () => sheet.showModal());
sheet.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => sheet.close("pick")));

/* ---------- Buttons, toasts, confirm ---------- */
document.getElementById("busy-demo").addEventListener("click", (e) => {
  const btn = e.currentTarget;
  setBusy(btn, true);
  setTimeout(() => setBusy(btn, false), 1600);
});
document.getElementById("toast-success").addEventListener("click", () => toast("Saved.", { type: "success" }));
document.getElementById("toast-error").addEventListener("click", () =>
  toast("Could not reach the server. Check your connection and try again.", { type: "error" }),
);
document.getElementById("toast-info").addEventListener("click", () => toast("Ordering is paused for now.", { type: "info" }));
document.getElementById("confirm-demo").addEventListener("click", async () => {
  const ok = await confirmDialog({
    title: "Cancel this order?",
    message: "This cannot be undone.",
    confirmLabel: "Cancel order",
    cancelLabel: "Keep order",
    danger: true,
  });
  toast(ok ? "Confirmed (demo only)." : "Nothing changed.", { type: ok ? "success" : "info" });
});

/* ---------- Inline validation pattern ---------- */
const table = document.getElementById("table-field");
const tableInput = table.querySelector("input");
const tableError = table.querySelector(".error-text");
function validateTable() {
  const bad = tableInput.value.trim() === "";
  table.dataset.invalid = String(bad);
  tableInput.setAttribute("aria-invalid", String(bad));
  tableError.hidden = !bad;
}
tableInput.addEventListener("blur", validateTable);
tableInput.addEventListener("input", () => tableInput.value.trim() && validateTable());
