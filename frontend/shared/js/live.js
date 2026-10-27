/* Keeps a page fresh by re-checking the server on a timer.
 * - Runs only while the tab is visible, and again straight away when it becomes visible.
 * - Skips a round while a dialog is open or a button is busy, so it never interrupts the person.
 * - Never overlaps itself: a slow request is not stacked on top of the next one.
 * - Drives a small "Live" badge: live, reconnecting (two failures in a row), paused (tab hidden).
 */
import { el } from "./ui.js";

const LABELS = { live: "Live", reconnecting: "Reconnecting…", paused: "Paused" };

export function liveBadge() {
  const text = el("span", { class: "live__text" }, LABELS.live);
  const root = el("span", { class: "live", "data-state": "live", role: "status", title: "This page updates by itself" },
    el("span", { class: "live__dot", "aria-hidden": "true" }), text);
  return {
    root,
    set(state) {
      root.dataset.state = state;
      text.textContent = LABELS[state];
    },
  };
}

/** Put the badge in the page heading (dashboard pages have one). */
export function attachBadge(badge, container = document.querySelector(".page-head")) {
  container?.append(badge.root);
}

export const defaultShouldSkip = () => Boolean(document.querySelector('dialog[open], [aria-busy="true"]'));

/**
 * @param refresh async () => void   throw to signal a failure
 * @returns { tick, stop }
 */
export function startLive({ refresh, intervalMs = 5000, badge, shouldSkip = defaultShouldSkip }) {
  let inFlight = false;
  let failures = 0;
  let stopped = false;

  async function tick() {
    if (stopped || document.hidden || inFlight || shouldSkip()) return;
    inFlight = true;
    try {
      await refresh();
      failures = 0;
      badge?.set("live");
    } catch {
      failures += 1;
      if (failures >= 2) badge?.set("reconnecting");
    } finally {
      inFlight = false;
    }
  }

  const timer = setInterval(tick, intervalMs);
  const onVisibility = () => {
    if (document.hidden) badge?.set("paused");
    else {
      badge?.set(failures >= 2 ? "reconnecting" : "live");
      tick();
    }
  };
  document.addEventListener("visibilitychange", onVisibility);

  return {
    tick,
    stop() {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    },
  };
}
