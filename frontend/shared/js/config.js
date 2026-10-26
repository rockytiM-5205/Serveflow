/* Frontend configuration. No secrets belong here: this file is public.
 *
 * apiBaseUrl is same-origin by default. The dev server and a production reverse proxy
 * both serve /api/v1 next to the pages, so session cookies and CSRF work without CORS.
 * Pointing this at a different origin also needs backend CORS and CSRF_TRUSTED_ORIGINS
 * settings (and credentialed requests); do that deliberately, not as a workaround.
 */
export const config = Object.freeze({
  apiBaseUrl: "/api/v1",
  requestTimeoutMs: 15000,
});
