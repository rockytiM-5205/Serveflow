// The live-refresh helper. Run from the frontend/ folder with: node --test
import assert from "node:assert/strict";
import test from "node:test";

import { startLive } from "../shared/js/live.js";

const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

function setup(t) {
  const state = { hidden: false, open: false, listeners: new Map() };
  globalThis.document = {
    get hidden() { return state.hidden; },
    addEventListener: (type, fn) => state.listeners.set(type, fn),
    removeEventListener: (type) => state.listeners.delete(type),
    querySelector: () => (state.open ? {} : null),
  };
  t.mock.timers.enable({ apis: ["setInterval"] });
  const badge = { states: [], set(s) { this.states.push(s); } };
  return { state, badge };
}

test("refreshes on every interval and reports Live", async (t) => {
  const { badge } = setup(t);
  let calls = 0;
  const live = startLive({ refresh: async () => { calls++; }, intervalMs: 5000, badge });
  t.mock.timers.tick(5000); await flush();
  t.mock.timers.tick(5000); await flush();
  assert.equal(calls, 2);
  assert.equal(badge.states.at(-1), "live");
  live.stop();
});

test("does nothing while the tab is hidden, and refreshes again when it returns", async (t) => {
  const { state, badge } = setup(t);
  let calls = 0;
  const live = startLive({ refresh: async () => { calls++; }, intervalMs: 5000, badge });
  state.hidden = true;
  t.mock.timers.tick(5000); await flush();
  assert.equal(calls, 0);
  state.listeners.get("visibilitychange")();
  assert.equal(badge.states.at(-1), "paused");
  state.hidden = false;
  state.listeners.get("visibilitychange")(); await flush();
  assert.equal(calls, 1);
  live.stop();
});

test("never stacks a slow refresh on top of the next one", async (t) => {
  const { badge } = setup(t);
  let calls = 0;
  let release;
  const live = startLive({ refresh: () => { calls++; return new Promise((r) => { release = r; }); }, intervalMs: 5000, badge });
  t.mock.timers.tick(5000); await flush();
  t.mock.timers.tick(5000); await flush();
  assert.equal(calls, 1);
  release(); await flush();
  t.mock.timers.tick(5000); await flush();
  assert.equal(calls, 2);
  live.stop();
});

test("waits while a dialog is open or something is busy", async (t) => {
  const { state, badge } = setup(t);
  let calls = 0;
  const live = startLive({ refresh: async () => { calls++; }, intervalMs: 5000, badge });
  state.open = true;
  t.mock.timers.tick(5000); await flush();
  assert.equal(calls, 0);
  state.open = false;
  t.mock.timers.tick(5000); await flush();
  assert.equal(calls, 1);
  live.stop();
});

test("shows Reconnecting after two failures in a row and recovers", async (t) => {
  const { badge } = setup(t);
  let fail = true;
  const live = startLive({ refresh: async () => { if (fail) throw new Error("offline"); }, intervalMs: 5000, badge });
  t.mock.timers.tick(5000); await flush();
  assert.deepEqual(badge.states, []);
  t.mock.timers.tick(5000); await flush();
  assert.equal(badge.states.at(-1), "reconnecting");
  fail = false;
  t.mock.timers.tick(5000); await flush();
  assert.equal(badge.states.at(-1), "live");
  live.stop();
});

test("stop ends the refreshing", async (t) => {
  const { badge } = setup(t);
  let calls = 0;
  const live = startLive({ refresh: async () => { calls++; }, intervalMs: 5000, badge });
  live.stop();
  t.mock.timers.tick(20000); await flush();
  assert.equal(calls, 0);
});
