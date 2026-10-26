import { ApiError, api } from "../../shared/js/api.js";
import { getSession } from "../../shared/js/auth.js";
import { el, emptyState, icon } from "../../shared/js/ui.js";
import { isValidSlug, slugify } from "../../shared/js/validators.js";
import { buildForm } from "../../shared/js/form-builder.js";
import { defaultTimezone, fulfilmentErrors, restaurantFields } from "./regional.js";
import { loginUrl, setActiveRestaurant } from "./shell.js";

const content = document.getElementById("content");
const customerUrl = (slug) => new URL(`../customer/index.html?r=${slug}`, location.href).href;
const SLUG_HINT = "Lowercase letters, numbers and hyphens. It can't be changed later.";

async function main() {
  let session;
  try {
    session = await getSession();
  } catch (err) {
    content.replaceChildren(emptyState({
      iconName: "alert",
      title: "Can't load your account",
      text: err instanceof ApiError ? err.message : "Something went wrong.",
      action: el("button", { class: "btn btn--secondary", type: "button", onclick: () => location.reload() }, icon("refresh"), "Try again"),
    }));
    return;
  }
  if (!session) {
    location.replace(loginUrl("create-restaurant.html"));
    return;
  }
  if (session.memberships.length) document.getElementById("back-link").hidden = false;
  if (!session.can_create_restaurant) {
    content.replaceChildren(emptyState({
      iconName: "lock",
      title: "This account can't create a restaurant",
      text: "Ask the platform administrator, or the owner of a restaurant to add you to theirs.",
    }));
    return;
  }

  const fields = restaurantFields({ includeSlug: true, timezone: defaultTimezone() });
  fields.find((f) => f.name === "slug").hint = SLUG_HINT;
  fields.find((f) => f.name === "slug").validate = (v) =>
    isValidSlug(v) ? null : "Use 3 to 63 lowercase letters, numbers or single hyphens.";

  const { form, controls } = buildForm({
    idPrefix: "cr",
    fields,
    values: { timezone: defaultTimezone(), pickup_enabled: true, dine_in_enabled: false, requires_table_number: false },
    submitLabel: "Create restaurant",
    validateForm: fulfilmentErrors,
    submit: (values) => api.post("/restaurants/", values),
    onSuccess: (restaurant) => {
      setActiveRestaurant(restaurant.slug);
      location.replace("index.html");
    },
  });

  const name = controls.get("name").input;
  const slug = controls.get("slug").input;
  const currency = controls.get("currency").input;
  const hint = document.getElementById("cr-slug-hint");
  let slugEdited = false;
  const refreshHint = () => {
    hint.textContent = slug.value ? `Customers will use: ${customerUrl(slug.value)}` : SLUG_HINT;
  };
  slug.addEventListener("input", () => {
    slugEdited = true;
    refreshHint();
  });
  name.addEventListener("input", () => {
    if (!slugEdited) {
      slug.value = slugify(name.value);
      refreshHint();
    }
  });
  currency.addEventListener("input", () => {
    currency.value = currency.value.toUpperCase();
  });
  content.replaceChildren(form);
  name.focus();
}

main();
