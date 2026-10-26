/* Pure helpers for the customer pages (no DOM). */

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Restaurant slug from "?r=<slug>", or null when missing or malformed. */
export function parseSlug(search) {
  const value = new URLSearchParams(search).get("r");
  if (!value) return null;
  const slug = value.trim().toLowerCase();
  return slug.length >= 3 && slug.length <= 63 && SLUG.test(slug) ? slug : null;
}

/** A tel: link built only from digits and a leading plus; null if nothing dialable remains. */
export function telHref(phone) {
  if (typeof phone !== "string") return null;
  const dialable = phone.replace(/[^\d+]/g, "");
  return /\d/.test(dialable) ? `tel:${dialable}` : null;
}
