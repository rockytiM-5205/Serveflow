import { ApiError } from "../../shared/js/api.js";
import { getOptions, signup } from "../../shared/js/auth.js";
import { el, emptyState, icon } from "../../shared/js/ui.js";
import { isValidEmail } from "../../shared/js/validators.js";
import { buildForm } from "../../shared/js/form-builder.js";

const mount = document.getElementById("signup");

async function main() {
  let options;
  try {
    options = await getOptions();
  } catch (err) {
    mount.replaceChildren(emptyState({
      iconName: "alert",
      title: "Can't reach the server",
      text: err instanceof ApiError ? err.message : "Something went wrong.",
      action: el("button", { class: "btn btn--secondary", type: "button", onclick: () => location.reload() }, icon("refresh"), "Try again"),
    }));
    return;
  }
  if (!options.self_service) {
    mount.replaceChildren(emptyState({
      iconName: "lock",
      title: "Account creation is turned off",
      text: "Ask the platform administrator to create an account for you.",
      action: el("a", { class: "btn btn--secondary", href: "login.html" }, "Sign in"),
    }));
    return;
  }

  const { form } = buildForm({
    idPrefix: "su",
    submitLabel: "Create account",
    fields: [
      { name: "first_name", label: "First name (optional)", type: "text", maxlength: 150, autocomplete: "given-name" },
      { name: "last_name", label: "Last name (optional)", type: "text", maxlength: 150, autocomplete: "family-name" },
      {
        name: "email", label: "Email", type: "email", required: true, maxlength: 254, autocomplete: "username",
        validate: (v) => (isValidEmail(v) ? null : "Enter a valid email address."),
      },
      {
        name: "password", label: "Password", type: "password", required: true, maxlength: 128, autocomplete: "new-password",
        hint: "At least 8 characters. Avoid common passwords and all-number passwords.",
      },
    ],
    submit: (values) => signup(values),
    onSuccess: (session) => location.replace(session.can_create_restaurant ? "create-restaurant.html" : "index.html"),
  });
  mount.replaceChildren(form);
}

main();
