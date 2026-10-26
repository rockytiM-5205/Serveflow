/* Staff session helpers. The session itself is an HttpOnly cookie managed by the backend. */
import { api, ApiError } from "./api.js";

/** The signed-in user and active memberships, or null when not signed in. */
export async function getSession(options) {
  try {
    return await api.get("/auth/me/", options);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

/** Fetches a CSRF cookie first (login is CSRF-protected), then signs in. */
export async function login(email, password) {
  await api.get("/auth/csrf/");
  return api.post("/auth/login/", { email, password });
}

export function logout() {
  return api.post("/auth/logout/");
}

/** Whether people can create accounts and restaurants themselves (public, no sign-in). */
export function getOptions() {
  return api.get("/auth/options/");
}

/** Creates an account and signs it in. Fetches the CSRF cookie first. */
export async function signup(values) {
  await api.get("/auth/csrf/");
  return api.post("/auth/signup/", values);
}
