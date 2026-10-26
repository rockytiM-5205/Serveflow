import { ApiError, api } from "../../shared/js/api.js";
import { el, emptyState, icon, setBusy, toast } from "../../shared/js/ui.js";
import { isValidEmail } from "../../shared/js/validators.js";
import { formDialog } from "./form-dialog.js";
import { ROLE_LABEL, displayName, hasRole } from "./session.js";
import { bootDashboard, handleSessionExpiry } from "./shell.js";

const HREF = "team.html";
const content = document.getElementById("content");

const skeleton = () =>
  el("div", { class: "card card__pad stack", "aria-hidden": "true" },
    ...[70, 55, 62].map((w) => el("div", { class: "skeleton skeleton--line", style: `width:${w}%;height:1.25rem` })));

function showError(err, retry) {
  if (err instanceof ApiError && err.status === 403) {
    content.replaceChildren(emptyState({
      iconName: "lock", title: "You don't have access to this page",
      text: "Your role for this restaurant may have changed. Reload to see your current access.",
    }));
    return;
  }
  content.replaceChildren(emptyState({
    iconName: "alert", title: "Couldn't load the team",
    text: err instanceof ApiError ? err.message : "Something went wrong.",
    action: el("button", { class: "btn btn--secondary", type: "button", onclick: retry }, icon("refresh"), "Try again"),
  }));
}

async function main() {
  const ctx = await bootDashboard({ href: HREF, minRole: "MANAGER" });
  if (!ctx) return;
  if (!ctx.allowed) {
    content.replaceChildren(emptyState({
      iconName: "lock", title: "Managers and owners only", text: "Your role doesn't include the team list.",
      action: el("a", { class: "btn btn--secondary", href: "index.html" }, "Back to overview"),
    }));
    return;
  }

  const isOwner = ctx.role === "OWNER";
  const me = ctx.session.user.id;
  const base = `/restaurants/${encodeURIComponent(ctx.restaurant.slug)}/members/`;
  const roleOptions = (isOwner ? ["STAFF", "MANAGER", "OWNER"] : ["STAFF"]).map((r) => ({ value: r, label: ROLE_LABEL[r] }));
  const canChange = (member) => member.user.id !== me && (isOwner || member.role === "STAFF");

  const failure = (err) => {
    if (handleSessionExpiry(err, HREF)) return;
    toast(err instanceof ApiError ? err.message : "Something went wrong.", { type: "error" });
  };

  async function addMember() {
    const fields = [
      {
        name: "email", label: "Email", type: "email", required: true, maxlength: 254,
        validate: (v) => (isValidEmail(v) ? null : "Enter a valid email address."),
      },
      { name: "first_name", label: "First name (optional)", type: "text", maxlength: 150 },
      { name: "last_name", label: "Last name (optional)", type: "text", maxlength: 150 },
    ];
    if (isOwner) fields.push({ name: "role", label: "Role", type: "select", options: roleOptions });
    fields.push({
      name: "password", label: "Starting password", type: "text", maxlength: 128, autocomplete: "off",
      hint: "Needed only if this person has no account yet. Share it privately; they can change it under Account.",
    });
    const saved = await formDialog({
      title: "Add a team member", fields, values: { role: "STAFF" }, submitLabel: "Add member",
      submit: (v) => api.post(base, Object.fromEntries(Object.entries(v).filter(([, value]) => value !== ""))),
    });
    if (saved) {
      toast("Member added.", { type: "success" });
      await loadPage(true);
    }
  }

  async function editMember(member) {
    const fields = isOwner ? [{ name: "role", label: "Role", type: "select", options: roleOptions }] : [];
    fields.push({ name: "is_active", label: "Can sign in to this restaurant", type: "checkbox" });
    const saved = await formDialog({
      title: `Edit ${displayName(member.user)}`, fields, values: { role: member.role, is_active: member.is_active },
      submit: (v) => api.patch(`${base}${member.id}/`, v),
    });
    if (saved) {
      toast("Member updated.", { type: "success" });
      await loadPage(true);
    }
  }

  function row(member) {
    const named = displayName(member.user) !== member.user.email;
    const actions = canChange(member)
      ? el("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-label": `Edit ${displayName(member.user)}`, onclick: () => editMember(member) }, "Edit")
      : null;
    return el("tr", { role: "row" },
      el("td", { role: "cell", "data-label": "Member" },
        el("div", {},
          el("span", { class: "member-name" }, displayName(member.user), member.user.id === me ? " (you)" : ""),
          named ? el("span", { class: "member-email muted" }, member.user.email) : null)),
      el("td", { role: "cell", "data-label": "Role" }, el("span", { class: "badge", "data-role": member.role }, ROLE_LABEL[member.role] ?? member.role)),
      el("td", { role: "cell", "data-label": "Status" },
        el("span", { class: "badge", "data-status": member.is_active ? "ACTIVE" : "INACTIVE" }, member.is_active ? "Active" : "Inactive")),
      el("td", { role: "cell", "data-label": "Actions" }, actions),
    );
  }

  const tbody = el("tbody", { role: "rowgroup" });
  const table = el("table", { class: "table table--stack", role: "table" },
    el("thead", { role: "rowgroup" }, el("tr", { role: "row" },
      ...["Member", "Role", "Status", "Actions"].map((h) => el("th", { role: "columnheader" }, h)))),
    tbody);
  const more = el("button", { class: "btn btn--secondary", type: "button", hidden: true }, "Load more");
  const toolbar = el("div", { class: "toolbar" },
    el("button", { class: "btn btn--primary", type: "button", onclick: addMember }, icon("plus"), "Add member"));
  const layout = [toolbar, el("div", { class: "table-wrap" }, table), more];
  let nextQuery = "";

  async function loadPage(reset) {
    try {
      const page = await api.get(base + (reset ? "" : nextQuery));
      if (reset) tbody.replaceChildren();
      tbody.append(...page.results.map(row));
      // The API returns an absolute URL; only its query string is used, so requests stay same-origin.
      nextQuery = page.next ? new URL(page.next, location.href).search : null;
      more.hidden = !nextQuery;
      if (!layout[1].isConnected) content.replaceChildren(...layout);
    } catch (err) {
      if (handleSessionExpiry(err, HREF)) return;
      if (!layout[1].isConnected) showError(err, () => { content.replaceChildren(skeleton()); loadPage(true); });
      else failure(err);
    }
  }

  more.addEventListener("click", async () => {
    setBusy(more, true);
    await loadPage(false);
    setBusy(more, false);
  });

  content.replaceChildren(skeleton());
  await loadPage(true);
}

main();
