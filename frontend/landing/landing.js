/* Landing page behaviour: mobile menu, optional photos, a gentle "live" demo in the mockup, current-section link. */
const toggle = document.querySelector(".nav-toggle");
const nav = document.getElementById("site-nav");

function setMenu(open) {
  nav.dataset.open = String(open);
  toggle.setAttribute("aria-expanded", String(open));
}
toggle.addEventListener("click", () => setMenu(nav.dataset.open !== "true"));
nav.addEventListener("click", (event) => {
  if (event.target.closest("a")) setMenu(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && nav.dataset.open === "true") {
    setMenu(false);
    toggle.focus();
  }
});

// Photos are optional: until a real image is added, the layout simply shows its colour block.
document.querySelectorAll("img[data-optional]").forEach((img) => {
  const missing = () => {
    img.hidden = true;
    img.parentElement.dataset.empty = "true";
  };
  img.addEventListener("error", missing, { once: true });
  if (img.complete && img.naturalWidth === 0) missing();
});

// The sample orders in the dashboard picture move along, the way a real queue does.
const STATUSES = [["Pending", "0"], ["Confirmed", "1"], ["Being served", "2"], ["Served", "3"]];
const pills = [...document.querySelectorAll(".mock .pill")];
if (pills.length && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
  let next = 0;
  setInterval(() => {
    if (document.hidden) return;
    const pill = pills[next % pills.length];
    next += 1;
    const index = STATUSES.findIndex(([, s]) => s === pill.dataset.s);
    const [label, code] = STATUSES[(index + 1) % STATUSES.length];
    pill.textContent = label;
    pill.dataset.s = code;
  }, 2600);
}

// Highlight the nav link of the section being read.
const links = new Map([...nav.querySelectorAll('a[href^="#"]')].map((a) => [a.getAttribute("href").slice(1), a]));
const spy = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    const current = entry.target.dataset.spyId;
    links.forEach((link, id) => link.setAttribute("aria-current", String(id === current)));
  });
}, { rootMargin: "-40% 0px -55% 0px" });
["top", "features", "how"].forEach((id) => {
  const target = id === "top" ? document.querySelector(".hero") : document.getElementById(id);
  if (target) {
    target.dataset.spyId = id;
    spy.observe(target);
  }
});

document.getElementById("year").textContent = new Date().getFullYear();
