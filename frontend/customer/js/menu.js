import { ApiError, api } from "../../shared/js/api.js";
import { closeOnBackdrop, el, emptyState, formatMoney, icon, toast } from "../../shared/js/ui.js";
import { isHttpsUrl } from "../../shared/js/validators.js";
import { startLive } from "../../shared/js/live.js";
import { createCart, describeCart, fromCents, loadLastOrder } from "./cart.js";
import { bootCustomer, show, skeleton } from "./restaurant.js";

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const MAX_QUANTITY = 99;

// Elements a render adds to <body>. They are removed before the next render, so a refresh never duplicates them.
let mounted = [];
const mount = (...nodes) => {
  document.body.append(...nodes);
  mounted.push(...nodes);
};
function unmount() {
  mounted.forEach((node) => node.remove());
  mounted = [];
  document.body.classList.remove("has-cart-bar");
}

function placeholder() {
  return el("div", { class: "media-placeholder", "aria-hidden": "true" }, icon("image", { large: true }));
}

function thumbnail(item) {
  const box = el("div", { class: "thumb" });
  if (isHttpsUrl(item.image_url)) {
    const img = el("img", { src: item.image_url, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
    img.addEventListener("error", () => img.replaceWith(placeholder()), { once: true });
    box.append(img);
  } else {
    box.append(placeholder());
  }
  return box;
}

/** A quantity stepper. data-role marks each control so focus can be put back after a re-render. */
function stepper({ name, quantity, onChange }) {
  const minus = el("button", { type: "button", "data-role": "minus", "aria-label": `Remove one ${name}`, onclick: () => onChange(-1) }, icon("minus"));
  const plus = el("button", {
    type: "button", "data-role": "plus", "aria-label": `Add one ${name}`, disabled: quantity >= MAX_QUANTITY, onclick: () => onChange(1),
  }, icon("plus"));
  return el("div", { class: "stepper", role: "group", "aria-label": `Quantity of ${name}` },
    minus, el("output", { "aria-live": "polite" }, String(quantity)), plus);
}

function main() {
  return bootCustomer().then(async (ctx) => {
    if (!ctx) return;
    const { slug, restaurant } = ctx;
    document.getElementById("back-link").href = `index.html?r=${encodeURIComponent(slug)}`;
    const lastOrder = loadLastOrder(slug);
    if (lastOrder) {
      const track = document.getElementById("track-link");
      track.href = `order.html?r=${encodeURIComponent(slug)}#${lastOrder}`;
      track.hidden = false;
    }
    show(el("div", { class: "menu-grid" }, ...Array.from({ length: 6 }, () => skeleton())));
    try {
      const menuUrl = `/restaurants/${encodeURIComponent(slug)}/menu/`;
      const menu = await api.get(menuUrl);
      render(menu, slug, restaurant);
      // Live: pick up sold-out items, price changes and the restaurant opening or closing for orders.
      let last = JSON.stringify([restaurant, menu]);
      startLive({
        intervalMs: 10000,
        refresh: async () => {
          const [info, fresh] = await Promise.all([api.get(`/restaurants/${encodeURIComponent(slug)}/`), api.get(menuUrl)]);
          const json = JSON.stringify([info, fresh]);
          if (json === last) return;
          last = json;
          const y = window.scrollY;
          render(fresh, slug, info);
          window.scrollTo(0, y);
        },
      });
    } catch (err) {
      show(emptyState({
        iconName: "alert", title: "Couldn't load the menu", text: err instanceof ApiError ? err.message : "Something went wrong.",
        action: el("button", { class: "btn btn--secondary", type: "button", onclick: () => location.reload() }, icon("refresh"), "Try again"),
      }));
    }
  });
}

function render(menu, slug, restaurant) {
  unmount();
  const { categories } = menu;
  const currency = menu.restaurant.currency;
  const chipNav = document.getElementById("chips");
  chipNav.replaceChildren();

  if (categories.length === 0) {
    show(emptyState({
      iconName: "utensils", title: "The menu isn't ready yet", text: "This restaurant hasn't added any dishes. Please check back later.",
      action: el("a", { class: "btn btn--secondary", href: `index.html?r=${encodeURIComponent(slug)}` }, "Back to restaurant"),
    }));
    return;
  }

  const itemsById = new Map(categories.flatMap((c) => c.items).map((item) => [item.id, item]));
  const ordering = restaurant.accepting_orders;
  document.getElementById("cart-button").hidden = !ordering;
  const cart = createCart(slug);
  if (ordering) {
    const removed = cart.reconcile(itemsById);
    if (removed.length) toast("Some items in your order aren't available any more, so we removed them.", { type: "info" });
  }

  // ---- food cards ----
  const cardRefreshers = [];

  function cardActions(item) {
    const box = el("div", { class: "food-card__actions" });
    if (!item.is_available) {
      box.append(el("button", { class: "btn btn--secondary btn--block", type: "button", disabled: true }, "Unavailable"));
      return box;
    }
    const paint = () => {
      const quantity = cart.quantity(item.id);
      if (box.dataset.quantity === String(quantity)) return;
      box.dataset.quantity = String(quantity);
      box.closest(".food-card")?.setAttribute("data-selected", quantity > 0 ? "true" : "false");
      if (quantity === 0) {
        box.replaceChildren(el("button", {
          class: "btn btn--primary btn--block", type: "button", "data-role": "plus", "aria-label": `Add ${item.name}`,
          onclick: () => { cart.change(item.id, 1); box.querySelector('[data-role="plus"]')?.focus(); },
        }, icon("plus"), "Add"));
      } else {
        box.replaceChildren(stepper({
          name: item.name, quantity,
          onChange: (delta) => {
            cart.change(item.id, delta);
            (box.querySelector(`[data-role="${delta > 0 ? "plus" : "minus"}"]`) ?? box.querySelector("button"))?.focus();
          },
        }));
      }
    };
    cardRefreshers.push(paint);
    paint();
    return box;
  }

  function foodCard(item) {
    const media = el("div", { class: "food-card__media" });
    if (isHttpsUrl(item.image_url)) {
      const img = el("img", { src: item.image_url, alt: item.name, loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
      img.addEventListener("error", () => img.replaceWith(placeholder()), { once: true });
      media.append(img);
    } else {
      media.append(placeholder());
    }
    if (!item.is_available) media.append(el("span", { class: "badge food-card__tag", "data-status": "UNAVAILABLE" }, "Unavailable"));
    const card = el("article", { class: "card food-card", "data-unavailable": item.is_available ? null : "true" },
      media,
      el("div", { class: "food-card__body" },
        el("h3", { class: "food-card__name" }, item.name),
        item.description ? el("p", { class: "food-card__desc" }, item.description) : null,
        el("p", { class: "price" }, formatMoney(item.price, currency), " ", el("span", { class: "price__unit" }, `/ ${item.unit_name}`)),
      ),
    );
    if (ordering) {
      const actions = cardActions(item);
      card.querySelector(".food-card__body").append(actions);
      // paint() ran before the card existed in the DOM; sync the selected state now.
      card.setAttribute("data-selected", cart.quantity(item.id) > 0 ? "true" : "false");
    }
    return card;
  }

  const sections = categories.map((category) => el("section", {
    id: `cat-${category.id}`, "data-id": category.id, class: "menu-section", "aria-labelledby": `cat-h-${category.id}`,
  },
    el("h2", { id: `cat-h-${category.id}` }, category.name),
    category.description ? el("p", { class: "muted" }, category.description) : null,
    el("div", { class: "menu-grid" }, ...category.items.map(foodCard)),
  ));

  // ---- category navigation ----
  const chips = new Map();
  const setCurrent = (id) => chips.forEach((chip, key) => chip.setAttribute("aria-current", String(key === String(id))));
  const goTo = (id) => {
    document.getElementById(`cat-${id}`).scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    setCurrent(id);
  };
  categories.forEach((category, index) => {
    const chip = el("button", { class: "chip", type: "button", "aria-current": String(index === 0), onclick: () => goTo(category.id) }, category.name);
    chips.set(String(category.id), chip);
    chipNav.append(chip);
  });
  const categorySheet = el("dialog", { class: "dialog", "aria-labelledby": "sheet-title" },
    el("div", { class: "dialog__panel" },
      el("h2", { id: "sheet-title" }, "Jump to category"),
      el("div", { class: "stack", style: "gap:var(--s-2)" },
        ...categories.map((category) => el("button", {
          class: "btn btn--secondary btn--block", type: "button", onclick: () => { categorySheet.close(); goTo(category.id); },
        }, category.name))),
      el("div", { class: "dialog__footer" }, el("button", { class: "btn btn--ghost", type: "button", onclick: () => categorySheet.close() }, "Close")),
    ),
  );
  closeOnBackdrop(categorySheet);
  const fab = el("button", { class: "btn btn--secondary fab", type: "button", onclick: () => categorySheet.showModal() }, icon("layers"), "Categories");

  const notice = ordering ? null : el("div", { class: "alert alert--warning", role: "note" }, icon("clock"),
    el("span", {}, "This restaurant isn't taking orders right now. You can still look at the menu."));
  show(el("div", { class: "stack" }, notice, ...sections));
  mount(categorySheet, fab);

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) setCurrent(entry.target.dataset.id);
  }, { rootMargin: "-25% 0px -65% 0px" });
  sections.forEach((section) => observer.observe(section));
  mounted.push({ remove: () => observer.disconnect() });

  if (ordering) mountCart(cart, itemsById, currency, slug, cardRefreshers);
}

/** The order summary: a bar at the bottom on small screens, the header button everywhere, and a sheet. */
function mountCart(cart, itemsById, currency, slug, cardRefreshers) {
  const headerButton = document.getElementById("cart-button");
  const headerCount = document.getElementById("cart-count");
  headerButton.hidden = false;

  const barCount = el("p", { class: "muted", style: "font-size:var(--fs-sm)" });
  const barTotal = el("p", { class: "price" });
  const bar = el("div", { class: "cart-bar", hidden: true },
    el("div", { class: "cart-bar__summary" }, barCount, barTotal),
    el("button", { class: "btn btn--primary", type: "button", onclick: () => openSheet() }, icon("bag"), "View order"));
  const sheetBody = el("div", { class: "stack" });
  const sheet = el("dialog", { class: "dialog", "aria-labelledby": "cart-title" },
    el("div", { class: "dialog__panel" },
      el("div", { class: "section-head", style: "margin:0" },
        el("h2", { id: "cart-title" }, "Your order"),
        el("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-label": "Close", onclick: () => sheet.close() }, icon("x"))),
      sheetBody));
  closeOnBackdrop(sheet);
  mount(bar, sheet);
  headerButton.onclick = () => openSheet();

  function openSheet() {
    renderSheet();
    sheet.showModal();
  }

  function renderSheet(focus) {
    const { lines, totalCents } = describeCart(cart, itemsById);
    if (lines.length === 0) {
      sheetBody.replaceChildren(el("p", { class: "muted" }, "Your order is empty. Add something from the menu."),
        el("button", { class: "btn btn--secondary btn--block", type: "button", onclick: () => sheet.close() }, "Back to the menu"));
      return;
    }
    sheetBody.replaceChildren(
      el("ul", { class: "cart-lines" }, ...lines.map(({ id, item, quantity, lineCents }) =>
        el("li", { class: "cart-line", "data-line": id },
          thumbnail(item),
          el("div", { class: "cart-line__main" },
            el("p", { class: "cart-line__name" }, item.name),
            el("p", { class: "muted price-sub" }, `${formatMoney(item.price, currency)} / ${item.unit_name}`),
            stepper({ name: item.name, quantity, onChange: (delta) => { cart.change(id, delta); renderSheet({ id, role: delta > 0 ? "plus" : "minus" }); } })),
          el("div", { class: "cart-line__side" },
            el("p", { class: "price" }, formatMoney(fromCents(lineCents), currency)),
            el("button", {
              class: "btn btn--ghost btn--sm", type: "button", "aria-label": `Remove ${item.name}`,
              onclick: () => { cart.set(id, 0); renderSheet(); },
            }, icon("trash"))))),
      ),
      el("div", { class: "total-row" }, el("span", {}, "Estimated total"), el("strong", { class: "price" }, formatMoney(fromCents(totalCents), currency))),
      el("p", { class: "muted", style: "font-size:var(--fs-sm)" }, "The restaurant works out the final total when you place the order."),
      el("a", { class: "btn btn--primary btn--block", href: `checkout.html?r=${encodeURIComponent(slug)}` }, "Checkout"),
    );
    if (focus) sheetBody.querySelector(`[data-line="${focus.id}"] [data-role="${focus.role}"]`)?.focus();
  }

  function update() {
    const { totalCents } = describeCart(cart, itemsById);
    const count = cart.count();
    headerCount.textContent = String(count);
    headerCount.hidden = count === 0;
    headerButton.setAttribute("aria-label", count ? `Your order, ${count} item${count === 1 ? "" : "s"}` : "Your order");
    barCount.textContent = `${count} item${count === 1 ? "" : "s"}`;
    barTotal.textContent = formatMoney(fromCents(totalCents), currency);
    bar.hidden = count === 0;
    document.body.classList.toggle("has-cart-bar", count > 0);
    cardRefreshers.forEach((paint) => paint());
  }
  cart.subscribe(update);
  update();
}

main();
