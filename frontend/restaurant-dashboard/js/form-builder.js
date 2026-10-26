/* Accessible form builder: fields, inline validation, server error mapping, no double submits.
 * Everything is inserted as text nodes; nothing is inserted as HTML. */
import { ApiError } from "../../shared/js/api.js";
import { el, icon, setBusy } from "../../shared/js/ui.js";

const INPUT_TYPES = new Set(["text", "email", "password", "tel"]);

/**
 * @param fields [{ name, label, type: "text"|"email"|"password"|"tel"|"textarea"|"select"|"checkbox", required, options,
 *                  hint, maxlength, inputmode, autocomplete, suggestions, cast: "number", validate(value) -> message|null }]
 * @param validateForm (values) -> { fieldName: message }   cross-field checks
 * @param submit async (values) => result   throw ApiError to show server errors
 * @returns { form, controls, setValue(name, value) }
 */
export function buildForm({
  idPrefix, fields, values = {}, submitLabel = "Save", submit, onSuccess, onCancel, validateForm,
  className = "stack", footerClass = "form-actions",
}) {
  const controls = new Map();
  const alertText = el("span");
  const alertBox = el("div", { class: "alert alert--danger", role: "alert", hidden: true }, icon("alert"), alertText);
  const form = el("form", { class: className, novalidate: true }, alertBox);

  for (const spec of fields) {
    const inputId = `${idPrefix}-${spec.name}`;
    const errorId = `${inputId}-error`;
    const hintId = `${inputId}-hint`;
    const error = el("p", { class: "error-text", id: errorId, hidden: true });
    const initial = values[spec.name];
    let input;
    let wrap;
    if (spec.type === "checkbox") {
      input = el("input", { type: "checkbox", id: inputId, checked: Boolean(initial) });
      wrap = el("div", { class: "field" }, el("label", { class: "check", for: inputId }, input, spec.label), error);
    } else {
      if (spec.type === "textarea") {
        input = el("textarea", { class: "textarea", id: inputId, maxlength: spec.maxlength });
      } else if (spec.type === "select") {
        input = el("select", { class: "select", id: inputId },
          ...spec.options.map((o) => el("option", { value: o.value }, o.label)));
      } else {
        const type = INPUT_TYPES.has(spec.type) ? spec.type : "text";
        input = el("input", {
          class: "input", id: inputId, type, maxlength: spec.maxlength, inputmode: spec.inputmode,
          autocomplete: spec.autocomplete ?? "off", autocapitalize: type === "email" ? "none" : null,
          spellcheck: type === "email" || type === "password" ? "false" : null,
          list: spec.suggestions ? `${inputId}-list` : null,
        });
      }
      input.value = initial ?? "";
      input.setAttribute("aria-describedby", spec.hint ? `${hintId} ${errorId}` : errorId);
      wrap = el("div", { class: "field" },
        el("label", { class: "label", for: inputId }, spec.label),
        input,
        spec.suggestions ? el("datalist", { id: `${inputId}-list` }, ...spec.suggestions.map((s) => el("option", { value: s }))) : null,
        spec.hint ? el("p", { class: "hint", id: hintId }, spec.hint) : null,
        error,
      );
    }
    controls.set(spec.name, { spec, input, wrap, error });
    form.append(wrap);
  }

  const setError = (name, message) => {
    const control = controls.get(name);
    control.wrap.dataset.invalid = message ? "true" : "false";
    control.input.setAttribute("aria-invalid", message ? "true" : "false");
    control.error.hidden = !message;
    control.error.textContent = message ?? "";
  };

  const read = () => Object.fromEntries([...controls].map(([name, { spec, input }]) => {
    if (spec.type === "checkbox") return [name, input.checked];
    const text = spec.type === "password" ? input.value : input.value.trim();
    return [name, spec.cast === "number" ? (text === "" ? null : Number(text)) : text];
  }));

  const validate = (vals) => {
    const crossField = validateForm ? validateForm(vals) : {};
    let first = null;
    for (const [name, { spec, input }] of controls) {
      const value = vals[name];
      const empty = value === "" || value === null;
      let message = null;
      if (spec.required && empty) message = `${spec.label} is required.`;
      else if (spec.validate && !empty) message = spec.validate(value);
      message ??= crossField[name] ?? null;
      setError(name, message);
      if (message && !first) first = input;
    }
    first?.focus();
    return !first;
  };

  const save = el("button", { class: `btn btn--primary${footerClass === "form-actions" ? " btn--block" : ""}`, type: "submit" }, submitLabel);
  const footer = el("div", { class: footerClass });
  if (onCancel) footer.append(el("button", { class: "btn btn--secondary", type: "button", onclick: onCancel }, "Cancel"));
  footer.append(save);
  form.append(footer);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (save.getAttribute("aria-busy") === "true") return;
    alertBox.hidden = true;
    const vals = read();
    if (!validate(vals)) return;
    setBusy(save, true);
    try {
      const result = await submit(vals);
      onSuccess?.(result);
    } catch (err) {
      let shown = false;
      if (err instanceof ApiError && err.code === "validation_error") {
        for (const [name, messages] of Object.entries(err.details ?? {})) {
          if (controls.has(name)) {
            setError(name, Array.isArray(messages) ? String(messages[0]) : String(messages));
            shown = true;
          }
        }
      }
      if (!shown) {
        alertText.textContent = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
        alertBox.hidden = false;
      }
      setBusy(save, false);
    }
  });

  return {
    form,
    controls,
    setValue(name, value) {
      controls.get(name).input.value = value;
    },
  };
}
