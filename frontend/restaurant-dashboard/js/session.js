/* Pure helpers (no DOM). Roles here only decide what the UI shows;
 * the backend re-checks every request. */
export const ROLE_RANK = { STAFF: 1, MANAGER: 2, OWNER: 3 };
export const ROLE_LABEL = { OWNER: "Owner", MANAGER: "Manager", STAFF: "Staff" };
export const PAGES = ["index.html", "orders.html", "menu.html", "settings.html", "team.html", "create-restaurant.html"];

export function hasRole(role, minRole) {
  const have = Object.hasOwn(ROLE_RANK, role) ? ROLE_RANK[role] : 0;
  const need = Object.hasOwn(ROLE_RANK, minRole) ? ROLE_RANK[minRole] : Infinity;
  return have >= need;
}

/** Only known dashboard pages are valid redirect targets (no open redirects). */
export function safeNext(value) {
  return PAGES.includes(value) ? value : "index.html";
}

export function pickMembership(memberships, storedSlug) {
  return memberships.find((m) => m.restaurant.slug === storedSlug) ?? memberships[0] ?? null;
}

export function displayName(user) {
  const name = `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim();
  return name || user.email;
}
