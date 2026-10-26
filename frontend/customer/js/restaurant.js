/* Loads the restaurant named by "?r=<slug>" and handles the not-found and error cases. */
import { ApiError, api } from "../../shared/js/api.js";
import { el, emptyState, icon } from "../../shared/js/ui.js";
import { parseSlug } from "./helpers.js";

const content = () => document.getElementById("content");

function show(node) {
  content().replaceChildren(node);
}

export function skeleton() {
  return el("div", { class: "card card__pad stack", "aria-hidden": "true" },
    el("div", { class: "skeleton skeleton--line", style: "width:55%;height:1.75rem" }),
    el("div", { class: "skeleton skeleton--line", style: "width:90%" }),
    el("div", { class: "skeleton skeleton--line", style: "width:70%" }),
  );
}

export async function bootCustomer() {
  const slug = parseSlug(location.search);
  if (!slug) {
    show(emptyState({
      iconName: "store",
      title: "Open your restaurant's link",
      text: "This page needs the link your restaurant gave you. Ask them for it, or scan their QR code again.",
    }));
    return null;
  }
  show(skeleton());
  try {
    const restaurant = await api.get(`/restaurants/${encodeURIComponent(slug)}/`);
    document.getElementById("brand-name").textContent = restaurant.name;
    document.getElementById("brand-link").href = `index.html?r=${encodeURIComponent(slug)}`;
    document.title = `${restaurant.name} · ServeFlow`;
    return { slug, restaurant };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      show(emptyState({
        iconName: "store",
        title: "We couldn't find this restaurant",
        text: "The link may be wrong or the restaurant isn't on ServeFlow right now. Check the link with the restaurant.",
      }));
      return null;
    }
    const retry = el("button", { class: "btn btn--secondary", type: "button", onclick: () => location.reload() },
      icon("refresh"), "Try again");
    show(emptyState({
      iconName: "alert",
      title: "Couldn't load the restaurant",
      text: err instanceof ApiError ? err.message : "Something went wrong.",
      action: retry,
    }));
    return null;
  }
}

export { show };
