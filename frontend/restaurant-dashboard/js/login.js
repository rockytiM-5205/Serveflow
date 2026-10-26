import { ApiError } from "../../shared/js/api.js";
import { getOptions, getSession, login } from "../../shared/js/auth.js";
import { setBusy } from "../../shared/js/ui.js";
import { safeNext } from "./session.js";

const params = new URLSearchParams(location.search);
const form = document.getElementById("login-form");
const submit = document.getElementById("submit");
const alertBox = document.getElementById("form-alert");
const alertText = document.getElementById("form-alert-text");
const fields = {
  email: { input: document.getElementById("email"), wrap: document.getElementById("field-email"), error: document.getElementById("email-error") },
  password: { input: document.getElementById("password"), wrap: document.getElementById("field-password"), error: document.getElementById("password-error") },
};

document.getElementById("expired").hidden = params.get("expired") !== "1";

function setFieldError(name, message) {
  const { input, wrap, error } = fields[name];
  wrap.dataset.invalid = message ? "true" : "false";
  input.setAttribute("aria-invalid", message ? "true" : "false");
  error.hidden = !message;
  error.textContent = message ?? "";
}

function clearErrors() {
  setFieldError("email", null);
  setFieldError("password", null);
  alertBox.hidden = true;
}

function showAlert(message) {
  alertText.textContent = message;
  alertBox.hidden = false;
}

function validate() {
  const email = fields.email.input.value.trim();
  let firstInvalid = null;
  if (!email) {
    setFieldError("email", "Enter your email address.");
    firstInvalid = fields.email.input;
  } else if (!/^\S+@\S+\.\S+$/.test(email)) {
    setFieldError("email", "Enter a valid email address.");
    firstInvalid = fields.email.input;
  }
  if (!fields.password.input.value) {
    setFieldError("password", "Enter your password.");
    firstInvalid ??= fields.password.input;
  }
  firstInvalid?.focus();
  return !firstInvalid;
}

function explain(err) {
  if (!(err instanceof ApiError)) return "Something went wrong. Please try again.";
  if (err.status === 401) return "Incorrect email or password.";
  if (err.status === 429) {
    const wait = err.retryAfter ? ` Try again in ${err.retryAfter} seconds.` : " Please wait a minute and try again.";
    return `Too many sign-in attempts.${wait}`;
  }
  if (err.code === "csrf_failed") return "Your browser session is out of date. Reload the page and try again.";
  if (err.code === "network_error" || err.code === "timeout") return err.message;
  return "Something went wrong. Please try again.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submit.getAttribute("aria-busy") === "true") return; // ignore double submits
  clearErrors();
  if (!validate()) return;

  setBusy(submit, true);
  try {
    await login(fields.email.input.value.trim(), fields.password.input.value);
    location.replace(safeNext(params.get("next")));
  } catch (err) {
    if (err instanceof ApiError && err.status === 400 && err.details) {
      const first = (value) => (Array.isArray(value) ? value[0] : value);
      if (err.details.email) setFieldError("email", first(err.details.email));
      if (err.details.password) setFieldError("password", first(err.details.password));
    }
    if (!fields.email.error.textContent && !fields.password.error.textContent) showAlert(explain(err));
    if (err instanceof ApiError && err.status === 401) {
      fields.password.input.value = "";
      fields.password.input.focus();
    }
    setBusy(submit, false);
  }
});

// Already signed in? Skip the form.
getSession()
  .then((session) => {
    if (session) location.replace(safeNext(params.get("next")));
  })
  .catch(() => {});

// Offer sign-up only when the backend has self-service turned on.
getOptions()
  .then((options) => {
    document.getElementById("signup-prompt").hidden = !options.self_service;
  })
  .catch(() => {});
