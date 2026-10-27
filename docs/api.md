# API reference (implemented endpoints)

Base path `/api/v1/`. Machine-readable schema: `/api/v1/schema/`; interactive docs: `/api/v1/docs/`
(Swagger UI loads its scripts from a CDN).

## Errors

Every error uses one shape:

```json
{"error": {"code": "not_a_member", "message": "...", "details": {}}}
```

`details` holds field errors for `validation_error`. Codes so far: `validation_error` (400),
`malformed_request` (400), `not_authenticated` (401), `authentication_failed` (401),
`csrf_failed` (403), `not_a_member` (403), `insufficient_role` (403), `permission_denied` (403),
`not_found` (404), `conflict` (409, e.g. `item_archived`, `duplicate_name`), `method_not_allowed` (405), `throttled` (429, with `Retry-After`).
Unauthenticated responses carry `WWW-Authenticate: Session`.

## Staff sign-in (session cookie + CSRF)

1. `GET /auth/csrf/` -> 204 and a `csrftoken` cookie.
2. `POST /auth/login/` with `{"email", "password"}` and header `X-CSRFToken: <cookie value>`.
   200 returns the session (below). The CSRF token rotates on login: re-read the cookie.
3. Every later write (`POST`/`PATCH`/`DELETE`) sends `X-CSRFToken`. Never store credentials in
   `localStorage`.
4. `POST /auth/logout/` -> 204.

Login is limited to 5 attempts per minute per IP and per email (429 `throttled`).

## Endpoints

| Method and path | Auth | Notes |
|---|---|---|
| `GET /auth/csrf/` | none | Sets the CSRF cookie |
| `POST /auth/login/` | none (CSRF required) | 200 session, 401 `authentication_failed` (same message for every failure) |
| `POST /auth/logout/` | session + CSRF | 204 |
| `GET /auth/me/` | session | `{"user": {id, email, first_name, last_name}, "memberships": [{"restaurant": {slug, name}, "role"}], "can_create_restaurant": bool}`; active memberships of active restaurants only |
| `GET /restaurants/{slug}/members/` | session, manager or owner of that restaurant | Cursor-paginated: `{"next", "previous", "results": [{id, user, role, is_active, created_at}]}`; `?page_size=` up to 100 |

Staff routes are authorized by an active membership in the restaurant named in the path,
re-checked on every request. An unknown slug and a non-member both get `403 not_a_member`.

## Public endpoints (no sign-in)

| Method and path | Notes |
|---|---|
| `GET /restaurants/{slug}/` | `slug, name, description, contact_phone, address, currency, timezone, accepting_orders, pickup_enabled, dine_in_enabled, requires_table_number`. Unknown and suspended restaurants both return 404 |
| `GET /restaurants/{slug}/menu/` | `{"restaurant": {slug, name, currency}, "categories": [{id, name, description, items: [{id, name, description, price, unit_name, is_available, image_url}]}]}`. Active categories with at least one non-archived item, ordered by `sort_order` then name; unavailable items are included with `is_available: false`. `price` is a decimal string such as `"2.50"` |

## Staff menu endpoints (session + CSRF; role is the minimum needed)

| Method and path | Role | Notes |
|---|---|---|
| `GET /restaurants/{slug}/menu/categories/` | staff | Array (not paginated), includes inactive categories |
| `POST /restaurants/{slug}/menu/categories/` | manager | `{name, description?, sort_order?, is_active?}`; names are unique per restaurant ignoring case |
| `GET`, `PATCH /restaurants/{slug}/menu/categories/{id}/` | staff, manager | |
| `GET /restaurants/{slug}/menu/items/` | staff | Array. Archived items hidden unless `?include_archived=1`; `?category={id}` filters |
| `POST /restaurants/{slug}/menu/items/` | manager | `{category, name, price, unit_name?, description?, image_url?, is_available?}`. `price` is a decimal string with at most 2 places, 0 or more. `image_url` must be `https://` or empty |
| `GET`, `PATCH /restaurants/{slug}/menu/items/{id}/` | staff, manager | Price changes are written to the audit log. Archived items return 409 `item_archived` |
| `POST /restaurants/{slug}/menu/items/{id}/archive/` | manager | Hides the item from customers; safe to repeat; audited |
| `PATCH /restaurants/{slug}/menu/items/{id}/availability/` | staff | `{"is_available": true|false}` |
| `GET /restaurants/{slug}/audit/` | manager | Cursor-paginated: `{id, action, entity_type, entity_id, metadata, actor_email, created_at}`, newest first |

Items are never deleted (orders will refer to them). A category can be hidden with `is_active: false`.
An id that belongs to another restaurant returns 404 on every detail route.

## Self-service onboarding (no Django admin needed)

Controlled by `DJANGO_SELF_SERVICE` (off unless set). Superusers can always create restaurants.

| Method and path | Auth | Notes |
|---|---|---|
| `GET /auth/options/` | none | `{"self_service": bool}`, so the sign-in page knows whether to offer sign-up |
| `POST /auth/signup/` | none (CSRF required) | `{email, password, first_name?, last_name?}`. 201 returns the session and signs the user in. 403 `signup_disabled` when off. Password must pass Django's validators. Limited to 10 per hour per IP. An existing email gets 400 on `email`, which does reveal that the account exists |
| `POST /auth/password/` | session + CSRF | `{current_password, new_password}` -> 204. This session stays signed in |
| `POST /restaurants/` | session + CSRF | `{name, slug, currency, timezone, description?, contact_phone?, address?, pickup_enabled?, dine_in_enabled?, requires_table_number?}`. 201; the caller becomes OWNER. `slug` is permanent. New restaurants have `accepting_orders: false`. 403 `restaurant_creation_unavailable` when off or the per-user limit (`MAX_RESTAURANTS_PER_USER`, 5) is reached |

## Settings and team management

| Method and path | Role | Notes |
|---|---|---|
| `GET /restaurants/{slug}/settings/` | staff | Name, contact details, currency, timezone, fulfilment options, `accepting_orders`, read-only `slug` |
| `PATCH /restaurants/{slug}/settings/` | staff for `accepting_orders` only; manager or owner for everything else | Staff sending any other field get 403 `insufficient_role`. Changes are audited by field name |
| `POST /restaurants/{slug}/members/` | manager (staff role only), owner (any role) | `{email, role?, first_name?, last_name?, password?}`. A new email creates an account and needs a starting password; an existing account is attached without one. 409 `already_member` |
| `PATCH /restaurants/{slug}/members/{id}/` | manager (staff members only), owner | `{role?, is_active?}`. You cannot change your own membership (403 `cannot_modify_self`). The last active owner cannot be removed (409 `last_owner`). Changes are serialised per restaurant and audited |

## Orders (guests order without an account)

Prices are always calculated by the server from the menu. A client can send only item ids and
quantities; any price, total or status it sends is ignored.

| Method and path | Auth | Notes |
|---|---|---|
| `POST /restaurants/{slug}/checkout/` | none; header `Idempotency-Key` required | `{customer_name, customer_phone, fulfilment_type: PICKUP\|DINE_IN, table_number?, notes?, items: [{menu_item_id, quantity}]}` (1-30 lines, quantity 1-99; repeated items are merged). 201 returns the order (see below) plus `token`. The key (16-64 letters, digits, `-`, `_`) is generated once per order attempt: a retry with the same key and body returns the original answer with `Idempotent-Replay: true`; the same key with a different body is 409 `idempotency_key_reused`. Limits: 30 per minute per IP, 20 per hour per phone per restaurant, 3 pending orders per phone per restaurant |
| `GET /orders/{token}/` | the token | Customer view: `code, status, payment_status, fulfilment_type, table_number, currency, subtotal, total, restaurant{slug,name}, items[{name, unit_name, unit_price, quantity, line_total}], timeline[{status, at}], cancellable, created_at, updated_at`. **No name, phone or notes.** Sent with `Cache-Control: no-store`. Bad, forged and revoked tokens all return the same 404. 600 per minute per IP (pages poll every 5 seconds, and a dining room can share one IP) |
| `POST /orders/{token}/cancel/` | the token | Only while `PENDING`; otherwise 409 `invalid_transition` |

Order creation errors: 409 `not_accepting_orders`, `fulfilment_disabled`, `item_unavailable` (`details.items`: `[{id, name?, reason: "not_found"|"unavailable"}]`), `too_many_open_orders`; 400 `validation_error` (e.g. `table_number` when the restaurant requires it).

The token is `<order uuid, 32 hex><HMAC, 64 hex>`, signed with `SECRET_KEY` (old keys listed in `SECRET_KEY_FALLBACKS` keep working). Raising `Order.token_version` revokes a link. The web pages keep it in the URL fragment so it never reaches server logs or referrers.

### Staff order endpoints (session + CSRF)

| Method and path | Role | Notes |
|---|---|---|
| `GET /restaurants/{slug}/orders/` | staff | Newest first, cursor-paginated. Filters: `status=PENDING,CONFIRMED`, `payment_status`, `fulfilment_type`, `business_date=YYYY-MM-DD`, `code=42`, `queue=1` (open orders plus served-but-unpaid). Rows have no phone number |
| `GET /restaurants/{slug}/orders/{public_id}/` | staff | Adds `customer_phone`, `notes`, `subtotal`, full `events` and `payments` |
| `POST .../orders/{public_id}/transitions/` | staff | `{to_status: CONFIRMED\|REJECTED\|SERVING\|SERVED, reason?, expected_status?}`. `REJECTED` needs a reason. A wrong step is 409 `invalid_transition`; a stale `expected_status` is 409 `stale_status` with `details.current_status` |
| `POST .../orders/{public_id}/cancel/` | staff before `SERVING`; manager or owner during it | `{reason, acknowledge_serving?, expected_status?}`. Reason required. While `SERVING`: staff get 403 `manager_required`, managers must send `acknowledge_serving: true`, and the action is audited. `SERVED`, `REJECTED` and `CANCELLED` orders cannot be cancelled |
| `POST .../orders/{public_id}/payment/` | staff | Header `Idempotency-Key` required. `{method: CASH\|TRANSFER, amount, reference?}`. Only for a `SERVED`, `UNPAID` order; `amount` must equal the total (400); one payment per order (409 `already_paid`, 409 `not_payable`). Audited |

Status flow: `PENDING -> CONFIRMED -> SERVING -> SERVED`; `PENDING -> REJECTED`; `PENDING/CONFIRMED/SERVING -> CANCELLED`.
Payment is separate: `UNPAID -> PAID`, only after `SERVED`. Every change is recorded in the order's history with who did it.
