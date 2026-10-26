/* Words and steps for an order's status (pure, no DOM). */
export const TERMINAL = new Set(["SERVED", "REJECTED", "CANCELLED"]);

export const HEADLINE = {
  PENDING: "Waiting for the restaurant",
  CONFIRMED: "Your order is confirmed",
  SERVING: "Your order is being served",
  SERVED: "Served. Enjoy your meal!",
  REJECTED: "The restaurant couldn't take this order",
  CANCELLED: "This order was cancelled",
};

export const DETAIL = {
  PENDING: "The restaurant will confirm your order shortly. This page updates by itself.",
  CONFIRMED: "The restaurant has accepted your order.",
  SERVING: "Your food is on its way.",
  SERVED: "",
  REJECTED: "You haven't been charged. You can place a new order or ask the restaurant.",
  CANCELLED: "",
};

const STEPS = [
  ["PENDING", "Order placed"],
  ["CONFIRMED", "Confirmed"],
  ["SERVING", "Being served"],
  ["SERVED", "Served"],
];

/** The happy-path steps with done/current flags, from the order's timeline. */
export function timelineSteps(order) {
  const reached = new Set(order.timeline.map((entry) => entry.status));
  const closed = order.status === "REJECTED" || order.status === "CANCELLED";
  return STEPS.map(([status, label]) => ({
    status,
    label,
    done: reached.has(status),
    current: !closed && order.status === status,
  }));
}

export const isTerminal = (status) => TERMINAL.has(status);

export function tokenFromHash(hash) {
  const token = String(hash ?? "").replace(/^#/, "");
  return /^[0-9a-f]{96}$/.test(token) ? token : null;
}
