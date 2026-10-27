# ServeFlow frontend

HTML5, modern CSS and vanilla JavaScript (ES modules). No framework, no build step, no
runtime dependencies.

**Status:** design system plus the staff sign-in, session and team pages, which use the real API.
Everything else waits for backend endpoints that don't exist yet (table below). `shared/design-system.html`
and `shared/shell-preview.html` are development previews with sample content only.

| Feature | Status | Endpoint(s) |
|---|---|---|
| Staff sign-in, sign-out, session check, expired-session redirect | Connected | `/auth/csrf/`, `/auth/login/`, `/auth/logout/`, `/auth/me/` |
| Restaurant switcher (users with several restaurants) | Connected | `/auth/me/` |
| Overview page (restaurant, role) | Connected | `/auth/me/` |
| Team list (managers and owners), cursor pagination | Connected | `/restaurants/{slug}/members/` |
| Customer restaurant page (`customer/index.html?r=<slug>`) | Connected | `/restaurants/{slug}/` |
| Customer menu: categories, food cards, photos with placeholder, unavailable items | Connected | `/restaurants/{slug}/menu/` |
| Dashboard menu management: categories and items, create/edit, availability switch, archive | Connected (staff can toggle availability; managers and owners edit) | `/restaurants/{slug}/menu/...` |
| Cart (bottom bar, header button, order sheet), checkout with pickup or dine-in and table number | Connected (needs the restaurant to be accepting orders) | `/restaurants/{slug}/orders/` |
| Order confirmation and live tracking (polls every 10 s, cancel while pending) | Connected | `/orders/{token}/`, `/orders/{token}/cancel/` |
| Staff order queue: confirm, reject, serve, cancel, record payment, details | Connected | `/restaurants/{slug}/orders/...` |
| Sign up, create your restaurant, "Set up your restaurant" onboarding (no Django admin) | Connected (needs `DJANGO_SELF_SERVICE=True`) | `/auth/options/`, `/auth/signup/`, `/restaurants/` |
| Settings: pause/resume orders (any staff), edit details (managers, owners), customer link | Connected | `/restaurants/{slug}/settings/` |
| Team: add members, change role, deactivate/reactivate | Connected | `/restaurants/{slug}/members/` |
| Change password | Connected | `/auth/password/` |
| Audit log screen | Not built (endpoint exists) | `/restaurants/{slug}/audit/` |

## Run locally

Start Django (see the root README), then from the repository root:

```powershell
py frontend\dev_server.py          # Windows
```

```bash
python3 frontend/dev_server.py     # macOS / Linux
```

Open http://localhost:5173/restaurant-dashboard/login.html (or `/` for an index). To sign in you need a
user who belongs to a restaurant: in Django admin create a Restaurant (currency and timezone are required),
a User, and a Restaurant membership. The dev server serves `frontend/` and proxies `/api/`,
`/admin/` and `/static/` to Django on port 8000 (`--backend` and `--port` change this).
Because everything is one origin, no CORS setup is needed in development and session
cookies and CSRF work as in production. Use `localhost`, not a LAN address, unless you add
that host to `DJANGO_ALLOWED_HOSTS`.

## Layout

```
frontend/
  index.html                   the public landing page
  dev.html                     development index (links to every page)
  landing/                     landing.css, landing.js, assets/ (optional photos)
  dev_server.py                static server + same-origin API proxy
  shared/
    css/  tokens, base, components, layout   (used by both apps)
    js/   config.js (API base URL), api.js (fetch client), auth.js, ui.js (DOM helpers, toast, dialogs, money)
    assets/icons.svg           hand-drawn icon sprite (replaceable)
    design-system.html         component preview (sample content only)
    shell-preview.html         staff dashboard shell: bottom tabs on phones, sidebar on desktop
  customer/                    restaurant page and menu (css/, js/); cart and checkout wait for orders
  restaurant-dashboard/        login, overview, menu, team (css/, js/); shell.js boots every page
  tests/                       node --test (API client, auth and session helpers)
```

## Conventions

- Design tokens only: colours, spacing, radii, shadows and motion come from `tokens.css`.
- API data is rendered with `textContent`, never as HTML.
- Prices shown in the browser are for display; the backend is authoritative.
- Demo data lives only in clearly labelled preview pages, never in production pages.
- Respects `prefers-reduced-motion`; touch targets are 44px.

## Getting started without Django admin

Set `DJANGO_SELF_SERVICE=True` in `.env` (the example file has it on for development), run Django and
`py frontend\dev_server.py`, then open `http://localhost:5173/restaurant-dashboard/signup.html`:

1. Create an account. You are signed in and sent to "Set up your restaurant".
2. Fill in the restaurant (the web address fills in from the name). You become its owner.
3. Add your menu under **Menu**, your staff under **Team**, and copy your customer link from **Settings**.

Everyone can then sign in at `login.html`. Django admin is only needed for platform-level work (suspending a
restaurant, resetting someone's password). To see the app with sample data instead, run
`python manage.py seed_demo --owner-email you@example.com` from `backend/` (development only).

Photos: paste an `https://` link into an item's "Photo link"; items without one show a placeholder.
The demo restaurant is open for orders, so you can place an order on the customer page, then confirm, serve and take payment for it in the dashboard.

## Tests

From `frontend/`: `node --test` (Node 20+, no dependencies). They cover the API client (CSRF header,
error envelope, timeouts, cancellation, bad responses), auth helpers and role/redirect helpers.
Page rendering and interaction are not covered by automated tests; check them in a browser.

## Security notes

- Sessions are an HttpOnly cookie; JavaScript never sees credentials. Only the chosen restaurant slug is kept in
  `localStorage`.
- Writes send the CSRF token from the `csrftoken` cookie. Login fetches it first (`/auth/csrf/`).
- Requests use `credentials: "same-origin"`. Serving the pages and `/api/` from one origin is the supported setup;
  anything else needs deliberate backend CORS/CSRF configuration.
- Role checks in the UI only hide controls; the backend enforces every permission.
- Redirect targets after sign-in are limited to known dashboard pages.

## Ordering notes

- The cart stores item ids and quantities only (in `localStorage`, per restaurant). Prices come from the menu each time and
  the server prices the real order; the total shown before placing is labelled an estimate.
- Each order attempt gets an `Idempotency-Key` that is kept for the same order, so retrying after a dropped connection can
  never place it twice.
- The order link is kept in the page address after `#`, so it is not sent to the server in page requests or referrers. The
  last order's link is also remembered in `localStorage` so the customer can find it again.
- The dashboard queue refreshes every 15 seconds while the tab is visible and flags new orders.

## Live updates

Every page that shows changing data re-checks the server by itself, only while its tab is visible, and never while a
dialog is open or a button is busy:

| Page | Refreshes |
|---|---|
| Dashboard: Orders (new orders flash, a toast appears, optional chime via the "Sound" button) | every 5 s |
| Dashboard: Overview (orders needing attention, "orders are off" notice) | every 5 s |
| Customer: order tracking | every 5 s, stops once the order is served, rejected or cancelled |
| Dashboard: Menu, Settings, Team | every 10 s |
| Customer: menu (sold-out items, prices, restaurant opening or closing) | every 10 s |

Pages show a small **Live** badge that turns to "Reconnecting…" after two failed checks and "Paused" while the tab is
hidden. The logic is `shared/js/live.js`. It uses plain polling, so it needs no extra server software; if you later want
instant pushes, that module is the single place to swap in server-sent events.

## Landing page

`index.html` is the public page: hero with dashboard and phone illustrations, how it works, why ServeFlow, a "built for
the rush" band, and a closing call to action. It links to sign-up, sign-in and the API documentation (`/api/v1/docs/`).
The illustrations are drawn in CSS (sample content, hidden from screen readers). Real photos are optional: see
`landing/assets/README.md`. It contains no invented statistics, testimonials or prices; add real ones when you have them.
