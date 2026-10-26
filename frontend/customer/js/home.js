import { el, icon } from "../../shared/js/ui.js";
import { loadLastOrder } from "./cart.js";
import { telHref } from "./helpers.js";
import { bootCustomer, show } from "./restaurant.js";

const ctx = await bootCustomer();
if (ctx) {
  const { slug, restaurant } = ctx;
  const facts = el("ul", { class: "facts" });
  if (restaurant.address) facts.append(el("li", {}, icon("store"), el("span", {}, restaurant.address)));
  const tel = telHref(restaurant.contact_phone);
  if (restaurant.contact_phone) {
    const label = tel ? el("a", { href: tel }, restaurant.contact_phone) : el("span", {}, restaurant.contact_phone);
    facts.append(el("li", {}, icon("user"), label));
  }

  const hero = el("section", { class: "card hero", "aria-labelledby": "restaurant-title" },
    el("h1", { id: "restaurant-title" }, restaurant.name),
    restaurant.description ? el("p", { class: "hero__lead" }, restaurant.description) : null,
    facts.children.length ? facts : null,
    el("div", { class: "row" },
      el("a", { class: "btn btn--primary", href: `menu.html?r=${encodeURIComponent(slug)}` },
        icon("utensils"), "View menu"),
      loadLastOrder(slug)
        ? el("a", { class: "btn btn--secondary", href: `order.html?r=${encodeURIComponent(slug)}#${loadLastOrder(slug)}` }, icon("clock"), "Track your order")
        : null,
    ),
  );
  show(hero);
}
