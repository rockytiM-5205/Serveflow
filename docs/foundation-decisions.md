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

## Known conflict

`AUTH_USER_MODEL = "accounts.User"` is set before the model exists, as requested.
Django's auth app resolves the user model during startup, so **`manage.py check`,
`pytest` and every other Django command fail until the User model is implemented**
(Stage 2). Expected message: `AUTH_USER_MODEL refers to model 'accounts.User' that has not been installed`.

## Deferred

CORS, throttling rates, error envelope, admin URL configuration, logging, static
serving, application server, CI.
