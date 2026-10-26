/* A form in a modal dialog. Resolves true when saved, false when cancelled. */
import { closeOnBackdrop, el } from "../../shared/js/ui.js";
import { buildForm } from "../../shared/js/form-builder.js";

let counter = 0;

export function formDialog({ title, description, fields, values = {}, submitLabel = "Save", submit, validateForm }) {
  return new Promise((resolve) => {
    const id = `fd-${++counter}`;
    const dialog = el("dialog", { class: "dialog", "aria-labelledby": `${id}-title` });
    const { form } = buildForm({
      idPrefix: id, fields, values, submitLabel, submit, validateForm,
      className: "dialog__panel", footerClass: "dialog__footer",
      onCancel: () => dialog.close("cancel"),
      onSuccess: () => dialog.close("saved"),
    });
    const heading = el("h2", { id: `${id}-title` }, title);
    form.prepend(heading);
    if (description) heading.after(el("p", { class: "muted" }, description));
    dialog.append(form);
    closeOnBackdrop(dialog);
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "saved");
      dialog.remove();
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}
