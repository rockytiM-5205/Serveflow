# Foundation decisions (Milestone 1, Part 1)

| Decision | Choice | Reason |
|---|---|---|
| Django version | 5.2 LTS | Long-term support; supported by DRF 3.18 |
| Settings layout | `config/settings/{base,development,testing,production}.py` | No duplication; production-only checks stay out of dev |
| Environment selection | `DJANGO_ENV` (default `production`) read by `manage.py`, `wsgi.py`, `asgi.py` | Fail-safe default; pytest forces testing via `--ds` |
| `.env` location | Repository root; real env vars win | One file for all tools; matches deployment practice |
| Database | PostgreSQL only; all `POSTGRES_*` variables required | No silent SQLite fallback |
| DRF defaults | Session auth, `IsAuthenticated`, JSON only | Deny by default; public views opt in explicitly |
| Static files | `STATIC_ROOT` set; no static-serving package yet | Serving strategy depends on the deployment decision |
| Primary keys | `BigAutoField` | Matches the approved schema |

## Known conflict (resolved by the Stage 2 User model)

`AUTH_USER_MODEL = "accounts.User"` is set before the model exists, as requested.
Django's auth app resolves the user model during startup, so **`manage.py check`,
`pytest` and every other Django command fail until the User model is implemented**
(Stage 2). Expected message: `AUTH_USER_MODEL refers to model 'accounts.User' that has not been installed`.

## Deferred

CORS, throttling rates, error envelope, admin URL configuration, logging, static
serving, application server, CI.

## Stage 2: User model decisions

| Decision | Choice | Reason |
|---|---|---|
| Base class | `AbstractBaseUser` + `PermissionsMixin` | Email login; `PermissionsMixin` is required for Django admin superusers. It adds `is_superuser`, `groups` and `user_permissions`, which go beyond the approved field list |
| Email uniqueness | Stored lowercase; `unique=True` plus DB CHECK `email = lower(email)` | Case-insensitive without the citext extension; DB enforces it even if `save()` is bypassed |
| Roles | `is_staff` / `is_superuser` = platform admin only | Restaurant roles live in RestaurantMembership; never authorize tenants with these flags |
| Required fields | none beyond email and password | Names optional |
| Accounts for customers | none | Guest ordering in the MVP |
| Deactivation | `is_active=False`, no deletes | Payments and orders protect their user references |

## Stage 3: Restaurant and membership decisions

| Decision | Choice | Reason |
|---|---|---|
| New restaurants | `accepting_orders=False`, `pickup_enabled=True` | Nothing is orderable until a restaurant is set up deliberately |
| Currency, timezone | No defaults | Per-restaurant facts; currency format is validated (`[A-Z]{3}`), not checked against the ISO list; timezone must be a valid IANA name |
| Fulfilment | At least one of pickup/dine-in enabled; `requires_table_number` only with dine-in | DB CHECK constraints |
| Slug | 3-63 chars, `[a-z0-9]` with single hyphens, reserved list blocked | DB CHECK plus validators; editing the reserved list needs a migration |
| Membership role | `OWNER`/`MANAGER`/`STAFF` (CHECK), default `STAFF`, unique per (restaurant, user) | Least privilege; a user may belong to several restaurants |
| Deletion | Restaurants and memberships cannot be deleted in admin; users are PROTECTed | Deactivate instead; keeps history intact |
| Last-owner rule | Validated in `clean()` only | Not race-safe and bypassable by `.update()`; the member-management service must enforce it under a row lock |

Not yet enforced: `slug`, `currency` and `timezone` immutability after a restaurant's
first order (orders do not exist yet).

## Self-service onboarding

| Decision | Choice | Reason |
|---|---|---|
| Who may create accounts and restaurants | Anyone, only when `DJANGO_SELF_SERVICE=True`; superusers always; max 5 owned restaurants per user | Lets restaurants set up without Django admin, but public sign-up is opt-in because it invites spam |
| Email verification | None | No email delivery yet. Anyone can register any address, so the address proves nothing about who they are |
| Adding team members | Managers add staff, owners add anyone; new accounts get a starting password set by the adder | No email invitations yet. Attaching an existing email reveals that the account exists |
| Last-owner rule | Enforced under a per-restaurant row lock in `services.change_member`; callers are re-read under the lock | Replaces the admin-only `clean()` check for API use |
| Slug | Permanent after creation | It is part of public links |

## Orders

| Decision | Choice | Confirm with the restaurant |
|---|---|---|
| Prices | Server-side only; the client sends ids and quantities | |
| Customer access | Signed token (HMAC of order id and version) in the link; no accounts | |
| Order codes | Three digits, restart each local day per restaurant | Yes: do they want a running number instead? |
| Customer cancellation | Immediate, only while the order is pending | Yes |
| Paying | Staff record payment after the order is served, full amount, cash or transfer | Yes: some restaurants take payment first |
| Cancelling a served-in-progress order | Managers and owners only, explicit acknowledgement, audited | |
| Phone numbers | Not verified. At most 3 pending orders per phone per restaurant | Yes |
| Retries | `Idempotency-Key` on order creation and payment; answers kept 48 hours | |
| Staff queue updates | Polling every 15 seconds, no push notifications or sound | |
| Not built | Refunds and voiding a payment, partial payments, delivery, online payment, customer accounts, receipts, notifications to customers | |
