import { api } from "../../shared/js/api.js";
import { el, icon, setBusy, toast } from "../../shared/js/ui.js";
import { ROLE_LABEL, hasRole } from "./session.js";
import { bootDashboard } from "./shell.js";

const ctx = await bootDashboard({ href: "index.html" });
if (ctx) {
  const content = document.getElementById("content");
  const { session, restaurant, role } = ctx;
  const customerUrl = new URL(`../customer/index.html?r=${encodeURIComponent(restaurant.slug)}`, location.href).href;

  content.append(el("section", { class: "card card__pad", "aria-label": "Your access" },
    el("dl", { class: "details" },
      el("dt", {}, "Restaurant"), el("dd", {}, restaurant.name),
      el("dt", {}, "Your role"), el("dd", {}, ROLE_LABEL[role] ?? role),
      el("dt", {}, "Signed in as"), el("dd", {}, session.user.email),
    ),
  ));
  content.append(el("div", { class: "row" },
    el("a", { class: "btn btn--primary", href: "orders.html" }, icon("list"), "Orders"),
    el("a", { class: "btn btn--secondary", href: "menu.html" }, icon("book"), "Menu"),
    hasRole(role, "MANAGER") ? el("a", { class: "btn btn--secondary", href: "team.html" }, icon("users"), "Manage team") : null,
    el("a", { class: "btn btn--secondary", href: customerUrl, target: "_blank", rel: "noopener" }, icon("store"), "View customer page"),
  ));
  // New restaurants start with orders OFF. Say so loudly, with a one-tap fix, or ordering looks broken.
  const base = `/restaurants/${encodeURIComponent(restaurant.slug)}`;
  const notice = el("div", {});
  content.prepend(notice);
  api.get(`${base}/settings/`)
    .then((settings) => {
      if (settings.accepting_orders) return;
      const turnOn = el("button", { class: "btn btn--primary btn--sm", type: "button" }, "Turn on orders");
      turnOn.addEventListener("click", async () => {
        setBusy(turnOn, true);
        try {
          await api.patch(`${base}/settings/`, { accepting_orders: true });
          notice.replaceChildren();
          toast("Orders are on. Customers can order now.", { type: "success" });
        } catch (err) {
          setBusy(turnOn, false);
          toast(err.message ?? "Couldn't turn orders on.", { type: "error" });
        }
      });
      notice.replaceChildren(el("div", { class: "alert alert--warning", role: "status" },
        icon("clock"),
        el("span", { style: "flex:1" }, "Customers can't place orders yet because orders are switched off. Add your menu, then turn them on."),
        turnOn));
    })
    .catch(() => {});

  // How many orders need attention right now (the first page of the queue).
  const queue = el("section", { class: "card card__pad", "aria-label": "Orders needing attention" }, el("p", { class: "muted" }, "Checking orders…"));
  content.append(queue);
  api.get(`${base}/orders/?queue=1`)
    .then((page) => {
      const count = page.results.length;
      const pending = page.results.filter((o) => o.status === "PENDING").length;
      queue.replaceChildren(
        el("h2", {}, count ? `${count}${page.next ? "+" : ""} order${count === 1 ? "" : "s"} need attention` : "Nothing needs attention"),
        el("p", { class: "muted" }, pending ? `${pending} waiting for confirmation.` : "New orders will show up on the Orders page."),
      );
    })
    .catch(() => queue.remove());
}
