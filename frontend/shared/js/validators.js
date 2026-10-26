/* Input checks shared by pages. They only give early feedback; the backend validates again. */

/** Up to 8 digits and an optional 1-2 decimal places, e.g. "5", "2.5", "12.50". */
export function isValidPrice(text) {
  return /^\d{1,8}(\.\d{1,2})?$/.test(text);
}

export function isValidSortOrder(value) {
  return Number.isInteger(value) && value >= 0 && value <= 32767;
}

export function isHttpsUrl(text) {
  if (typeof text !== "string") return false;
  try {
    const url = new URL(text);
    return url.protocol === "https:" && url.hostname !== "";
  } catch {
    return false;
  }
}

/** "Green Bowl & Grill" -> "green-bowl-grill" (letters and digits, single hyphens, at most 63 characters). */
export function slugify(text) {
  return String(text ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63)
    .replace(/-+$/g, "");
}

export function isValidSlug(text) {
  return typeof text === "string" && text.length >= 3 && text.length <= 63 && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(text);
}

export function isValidEmail(text) {
  return typeof text === "string" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text);
}
