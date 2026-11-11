# RestroOS

RestroOS is a multi-tenant restaurant management SaaS. This repository contains
**Phase 1 and Phase 2** only: the platform foundation, authentication, tenancy,
role-based access control, isolation tests, and a functional owner/staff web
app.

Phase 3+ (menus, orders, kitchen display, inventory, payments, analytics,
WebSockets) is intentionally **not** implemented yet. The schema and permission
model leave room for it, but no mock order or sales data is shipped.

---

## What works today

| Area | Status |
| --- | --- |
| Self-service registration (tenant + first branch + owner membership + Free plan) | ✅ |
| Email/password login, logout, session bootstrap | ✅ |
| Short-lived JWT access token + rotating opaque refresh token | ✅ |
| Refresh-token family reuse detection and revocation | ✅ |
| Multi-tenant membership with tenant-wide and branch-scoped roles | ✅ |
| Business/context switcher (owner of several businesses, branch switching) | ✅ |
| Staff invitations (email-bound, single-use, 7-day expiry) | ✅ |
| Membership suspend / reactivate / remove (sessions revoked) | ✅ |
| Branch listing/creation with plan limits | ✅ |
| Plan/subscription inspection (Free plan seeded at startup) | ✅ |
| Audit log for security-relevant actions | ✅ |
| PostgreSQL row-level security as defence in depth | ✅ (Postgres only) |
| React SPA: login, register, dashboard, staff, invitation acceptance | ✅ |

Not implemented: menus, orders, kitchen, inventory, analytics, email delivery,
password reset, payment gateway, and any hard-coded demo data.

---

## Architecture

```
restroos/
├── apps/
│   ├── api/                     FastAPI modular monolith
│   │   ├── app/
│   │   │   ├── api/v1/          Versioned router composition
│   │   │   ├── core/            Settings, DB, security, deps, errors, RBAC
│   │   │   ├── db/              SQLAlchemy base, types, model registry
│   │   │   └── modules/
│   │   │       ├── auth/        Users, refresh tokens, registration/login
│   │   │       ├── tenants/     Tenants, restaurants, memberships, invitations
│   │   │       ├── staff/       Invite/manage staff and memberships
│   │   │       ├── billing/     Plans and subscriptions
│   │   │       └── audit/       Append-only audit log
│   │   ├── alembic/             Async migrations (schema + RLS policies)
│   │   └── tests/               unit / integration / isolation suites
│   └── web/                     React 18 + TypeScript + Vite + Tailwind SPA
├── infra/postgres/              Runtime-role grants and hardening SQL
├── docker-compose.yml           Local PostgreSQL 16
└── .github/workflows/ci.yml     Lint, SQLite tests, Postgres RLS, web build
```

Key design choices:

- **Modular monolith.** One API process, one SPA. Modules own their models,
  schemas, services, and routers, so a future split is a refactor, not a
  rewrite.
- **Shared-schema tenancy.** Every business row carries `tenant_id`; services
  filter by the authenticated context. PostgreSQL RLS is a second layer that
  fails closed if a query forgets that filter.
- **UUIDv7 primary keys.** Time-ordered, avoids leaking row counts, and works
  with the Postgres `uuid` type.
- **Money in minor units.** Integers (paise), never floats. Currency is
  per-tenant (INR by default).
- **UTC everywhere.** `UTCDateTime` normalizes values; API responses are
  ISO-8601 with `Z`/offset.

---

## Quick start (Windows 11, SQLite)

### 1. Backend

```powershell
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

- API: <http://127.0.0.1:8000>
- OpenAPI docs: <http://127.0.0.1:8000/docs> (disabled in production)
- Health: `GET /health`, readiness: `GET /ready`

The Free plan is seeded automatically on startup from
`FREE_PLAN_MAX_RESTAURANTS` / `FREE_PLAN_MAX_STAFF`.

### 2. Frontend

In a second terminal:

```powershell
cd apps\web
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to
`http://127.0.0.1:8000`, so no CORS configuration is needed in development.
Set `VITE_API_URL` only if the API lives elsewhere.

### 3. First use

1. Open `/register` and create a business. The first user becomes the owner.
2. The dashboard shows the business, plan limits, and branches.
3. Create additional branches (subject to the plan limit).
4. Invite staff. The API deliberately has no email sender yet, so the UI shows
   a single-use invitation link. Open it in a browser, sign in (or register)
   with the invited email, and accept.

---

## Testing

Run from `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests
```

The SQLite suite covers auth, token rotation/reuse, RBAC, tenancy, staff
limits, invitations, and cross-tenant access. PostgreSQL RLS tests are skipped
unless `TEST_POSTGRES_URL` is set:

```powershell
$env:TEST_POSTGRES_URL = "postgresql+asyncpg://restroos_app:restroos_app_dev_password@localhost:5432/restroos"
.\.venv\Scripts\python.exe -m pytest tests\isolation\test_postgres_rls.py -q
```

They require a database prepared exactly like the CI job:

1. `infra/postgres/init.sql` creates the low-privilege `restroos_app` role.
2. `alembic upgrade head` runs **as the schema owner** (Alembic needs DDL).
3. `infra/postgres/harden.sql` makes audit history append-only.

Frontend:

```powershell
cd apps\web
npm run build     # tsc --noEmit && vite build
npm run typecheck
```

---

## PostgreSQL (production-like local setup)

```powershell
docker compose up -d
```

The container creates the `restroos` database and the `restroos_owner` role,
then runs `infra/postgres/init.sql` to create the runtime role. Init scripts only
run against an empty data volume; `init.sql` is idempotent, so you can re-apply
it at any time from the repo root:

```powershell
Get-Content infra\postgres\init.sql |
  docker exec -i restroos-postgres psql -U restroos_owner -d restroos -v ON_ERROR_STOP=1 -f /dev/stdin
```

Migrations must run as the owner, because the runtime role cannot change the
schema:

```powershell
cd apps\api
$env:DATABASE_URL = "postgresql+asyncpg://restroos_owner:restroos_owner_dev_password@localhost:5432/restroos"
.\.venv\Scripts\alembic.exe upgrade head

# Apply runtime hardening once per environment after migrations.
Get-Content ..\..\infra\postgres\harden.sql |
  docker exec -i restroos-postgres psql -U restroos_owner -d restroos -v ON_ERROR_STOP=1 -f /dev/stdin
```

Then start the API with the **runtime** role:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://restroos_app:restroos_app_dev_password@localhost:5432/restroos"
.\.venv\Scripts\uvicorn.exe app.main:app --port 8000
```

Why two roles: PostgreSQL table owners bypass row-level security unless
`FORCE ROW LEVEL SECURITY` is used. Keeping the app on a non-owner role makes
every policy enforceable. `FORCE` is intentionally not used because migrations
must still be able to operate on tables as the owner.

Production checklist:

- `ENVIRONMENT=production`
- `DATABASE_URL` uses `postgresql+asyncpg://`
- `JWT_SECRET` is a fresh random value of at least 32 characters
- `COOKIE_SECURE=true` (HTTPS) and exact `CORS_ORIGINS`
- Run `harden.sql`; put the API behind a reverse proxy that sets HSTS
- Replace the in-memory rate limiter with a shared store (Redis) when running
  more than one API process

---

## Security model

### Authentication

- Argon2id password hashes.
- HS256 access JWT, 15 minutes, carrying `sub`, tenant, membership, role, and
  scope claims. The SPA keeps it in memory only, never in `localStorage`.
- Opaque refresh token (32 random bytes), stored as a SHA-256 digest, valid
  14 days, rotated on every refresh.
- Refresh cookie: `HttpOnly`, `SameSite=Lax`, `Path=/api/v1/auth`, `Secure` in
  production.
- Reuse of an already-rotated refresh token revokes the whole token family and
  is recorded in the audit log.
- Login/register/refresh are rate limited per client IP.

### Tenancy and RBAC

Roles: `owner`, `manager`, `cashier`, `waiter`, `kitchen`, `inventory`,
`viewer`.

- Owners and managers can hold tenant-wide memberships; other roles are
  typically branch-scoped.
- A membership is either tenant-wide (`restaurant_id IS NULL`) or bound to one
  branch.
- Permissions are checked from the role, not from client input.
- Cross-tenant object access returns **404**, not 403, so IDs do not reveal
  existence.
- Suspending or removing a membership revokes that member's refresh tokens.
- Only owners may assign the `owner`/`manager` roles; managers may assign the
  operational roles below them.

Permission codes are defined in `apps/api/app/core/permissions.py` and are
returned to the SPA with the session, so the UI hides actions the user cannot
perform. The server still re-checks every request.

### Database isolation

On PostgreSQL, RLS is enabled for `restaurants`, `subscriptions`,
`invitations`, `memberships`, `audit_logs`, and `tenants`. Policies read
transaction-local settings:

```sql
set_config('app.tenant_id', '<uuid>', true)
set_config('app.user_id', '<uuid>', true)
set_config('app.invitation_token', '<sha256>', true)
```

- Tenant tables require `tenant_id = app.tenant_id` for reads and writes.
- `memberships` additionally allows a user to read their own rows (needed for
  login/tenant switching).
- `tenants` additionally allows reading tenants where the user has an active
  membership.
- `invitations` additionally allows reading the single invitation matching the
  presented token digest.
- With no context set, every policy evaluates to false — queries fail closed.
- `users`, `plans`, and `refresh_tokens` are intentionally not tenant-RLS:
  authentication must look them up before a tenant context exists. They are
  protected by token-hash lookups, uniqueness constraints, and app-layer
  scoping instead.

`tests/isolation/test_cross_tenant.py` verifies app-level isolation on SQLite;
`tests/isolation/test_postgres_rls.py` verifies the database layer on Postgres.

---

## API overview

All routes are under `/api/v1`. Errors use RFC 7807
`application/problem+json` with a stable `code`.

| Method | Path | Access |
| --- | --- | --- |
| POST | `/auth/register` | public (creates tenant, branch, owner, Free subscription) |
| POST | `/auth/login` | public |
| POST | `/auth/refresh` | refresh cookie |
| POST | `/auth/logout` | authenticated |
| GET | `/auth/me` | authenticated |
| POST | `/auth/switch-context` | authenticated |
| GET | `/tenant` | `tenant:read` |
| PATCH | `/tenant` | `tenant:manage`, tenant-wide |
| GET | `/restaurants` | `branch:read` |
| POST | `/restaurants` | `branch:manage`, tenant-wide |
| GET | `/restaurants/{id}` | `branch:read` |
| GET | `/billing/subscription` | `billing:read` |
| GET | `/staff` | `staff:read` |
| POST | `/staff/invitations` | `staff:invite` |
| GET | `/staff/invitations` | `staff:read` |
| POST | `/staff/invitations/accept` | authenticated, matching email |
| DELETE | `/staff/invitations/{id}` | `staff:invite` |
| PATCH | `/staff/{membership_id}` | `staff:manage` |
| DELETE | `/staff/{membership_id}` | `staff:manage` |

Registration payload:

```json
{
  "email": "owner@example.com",
  "password": "at-least-10-characters",
  "full_name": "Asha Rao",
  "business_name": "Spice Route Hospitality",
  "restaurant_name": "Indiranagar",
  "timezone": "Asia/Kolkata"
}
```

For invitation acceptance, send `invitation_token` instead of
`business_name`.

---

## Configuration

See `apps/api/.env.example`. Important values:

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` enables strict checks |
| `DATABASE_URL` | SQLite file | Production must be `postgresql+asyncpg://` |
| `JWT_SECRET` | dev value | ≥32 chars; must be replaced in production |
| `ACCESS_TOKEN_MINUTES` | `15` | |
| `REFRESH_TOKEN_DAYS` | `14` | |
| `COOKIE_SECURE` | `false` | Must be `true` in production |
| `COOKIE_SAMESITE` | `lax` | |
| `CORS_ORIGINS` | localhost:5173 | Comma-separated exact origins |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `20` | Per IP + route |
| `FREE_PLAN_MAX_RESTAURANTS` | `1` | Seeded at startup |
| `FREE_PLAN_MAX_STAFF` | `5` | Pending invitations count |
| `TEST_POSTGRES_URL` | unset | Enables Postgres RLS tests |

Production startup refuses a default `JWT_SECRET`, a non-PostgreSQL
`DATABASE_URL`, `COOKIE_SECURE=false`, or wildcard CORS.

---

## Limitations and next steps

- No email provider yet; invitation links are displayed once in the UI.
- No password reset / email verification yet.
- Payment recording is deliberately manual-only in later phases; card details
  must never be stored.
- Rate limiting and request IDs are per-process. Use Redis and a shared request
  log before scaling horizontally.
- No background worker: audit writes, token rotation, and plan seeding happen
  in-request/at startup.
- Phase 3 modules (menu, orders, kitchen display, inventory, analytics,
  WebSockets) are not implemented.

---

## Useful commands

| Task | Command (from `apps/api`) |
| --- | --- |
| Migrate | `.\.venv\Scripts\alembic.exe upgrade head` |
| New migration | `.\.venv\Scripts\alembic.exe revision --autogenerate -m "message"` |
| Downgrade one revision | `.\.venv\Scripts\alembic.exe downgrade -1` |
| Tests | `.\.venv\Scripts\python.exe -m pytest -q` |
| Lint | `.\.venv\Scripts\ruff.exe check app tests` |
| Dev server | `.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000` |

| Task | Command (from `apps/web`) |
| --- | --- |
| Dev server | `npm run dev` |
| Type check | `npm run typecheck` |
| Production build | `npm run build` |
| Preview build | `npm run preview` |
