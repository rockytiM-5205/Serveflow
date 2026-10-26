/* Small fetch wrapper for the ServeFlow API.
 * - JSON in and out; every failure becomes an ApiError with the backend's error envelope.
 * - Sends the CSRF token (from the csrftoken cookie) on unsafe methods.
 * - Same-origin cookies only (credentials: "same-origin"); nothing is stored in JS.
 * - Timeout and caller cancellation via AbortController.
 */
import { config } from "./config.js";

export class ApiError extends Error {
  constructor({ status = 0, code = "error", message = "Something went wrong.", details = {}, retryAfter = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status; // 0 when the server was never reached
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter; // seconds, from Retry-After (429)
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name) {
  const prefix = `${name}=`;
  for (const part of document.cookie.split("; ")) {
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length));
  }
  return null;
}

function errorFrom(response, data) {
  const envelope = data && typeof data === "object" ? data.error : null;
  const retry = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
  return new ApiError({
    status: response.status,
    code: envelope?.code ?? "http_error",
    message: envelope?.message ?? `Request failed (${response.status}).`,
    details: envelope?.details ?? {},
    retryAfter: Number.isFinite(retry) ? retry : null,
  });
}

export async function request(path, { method = "GET", body, signal, timeoutMs = config.requestTimeoutMs, headers: extraHeaders = {} } = {}) {
  const headers = { Accept: "application/json", ...extraHeaders };
  const init = { method, headers, credentials: "same-origin", cache: "no-store" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onCallerAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onCallerAbort, { once: true });
  }
  init.signal = controller.signal;

  try {
    const response = await fetch(config.apiBaseUrl + path, init);
    if (response.status === 204) return null;
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    if (!response.ok) throw errorFrom(response, data);
    if (data === null) {
      // 2xx without JSON usually means the base URL points at the wrong server.
      throw new ApiError({ status: response.status, code: "invalid_response", message: "The server sent an unexpected response." });
    }
    return data;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (timedOut) throw new ApiError({ code: "timeout", message: "The server took too long to respond." });
    if (signal?.aborted) throw err; // the caller cancelled; let them see the AbortError
    throw new ApiError({ code: "network_error", message: "Can't reach the server. Check your connection and try again." });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }
}

export const api = {
  get: (path, options) => request(path, { ...options, method: "GET" }),
  post: (path, body, options) => request(path, { ...options, method: "POST", body }),
  patch: (path, body, options) => request(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => request(path, { ...options, method: "DELETE" }),
};
