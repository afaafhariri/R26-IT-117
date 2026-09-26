# Gateway — R26-IT-117 API entry point

FastAPI service on port **8080**, and the only service the browser talks to.
It handles accounts and sessions itself (`/api/auth/*`) and forwards
everything under `/api/<service>/` to the matching component, but only for a
signed-in user. The components need no changes and no auth code of their own.

| Gateway path | Forwarded to | Default |
|---|---|---|
| `/api/c01/…` | C01 Architecture | `http://localhost:8001` |
| `/api/c02/…` | C02 Cost Estimation | `http://localhost:8002` |
| `/api/c03/…` | C03 Timeline | `http://localhost:8000` |
| `/api/c04/…` | C04 Performance | `http://localhost:5004` |

For example, `POST /api/c02/estimate` becomes `POST /estimate` on C02.

## Accounts and sessions

| Endpoint | What it does |
|---|---|
| `POST /api/auth/signup` | Creates the account and emails a confirmation link. Always answers 202 with the same message. |
| `POST /api/auth/verify-email` | Confirms the address and signs in. Needs the link's token **and** the password. |
| `POST /api/auth/verify-email/resend` | Emails a new confirmation link. |
| `POST /api/auth/login` | Signs in (optionally "remember me"). Refused until the email is confirmed. |
| `POST /api/auth/logout` | Ends the session on the server and clears the cookie. |
| `GET /api/auth/me` | The signed-in user, or 401. |
| `POST /api/auth/password/forgot` | Emails a reset link. Always answers 202 with the same message. |
| `POST /api/auth/password/reset` | Sets a new password and signs out every device. |

How it is kept safe:

- **Passwords** are hashed with Argon2id. The only rule is 12–128 characters
  (no "must contain a symbol"). An unknown email takes as long to reject as a
  wrong password.
- **No account discovery.** Sign-up, "resend link" and "forgot password"
  answer identically whether or not the address has an account; only the
  inbox learns the difference. A wrong password and an unknown email give the
  same error.
- **Sessions** are server-side. The cookie (`__Host-session`: HttpOnly,
  Secure, SameSite=Lax) holds a random ID, and the database stores only its
  SHA-256, so ending a session is instant. Lifetimes: 2 h idle / 12 h total,
  or 7 days idle / 30 days total with "remember me". A new ID is issued at
  every login.
- **Email links** are single-use, stored hashed, and expire (confirmation
  24 h, reset 30 min). The token travels in the URL `#fragment`, which is
  never sent to a server or leaked in a `Referer`. Requesting a new link kills
  the old one.
- **Pre-hijacking is blocked.** If someone signs up with your address first,
  confirming needs *their* password, so your click activates nothing. The
  "you already have an account" email points you to a reset, which makes the
  account yours.
- **CSRF**: besides SameSite, every POST/PUT/PATCH/DELETE must come from our
  own origin (`Sec-Fetch-Site`, or `Origin` against `ALLOWED_ORIGINS`).
- **Rate limits** per IP and per email on sign-up, login, confirmation,
  resends and resets, answered with 429 and `Retry-After`.
- **The proxy** never forwards the browser's cookies to a service, and never
  lets a service set cookies or CORS headers on the gateway's origin.

Every user also gets a row in `accounts`: the billing entity that
subscriptions will attach to later.

## Running locally

Needs Postgres with the `authdb` database and `gateway` login. To create them
(once), as a superuser:

```bash
psql -d postgres -v gateway_password='choose-a-password' -f gateway/db/create_authdb.sql
```

Then:

```bash
cd gateway
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # set DATABASE_URL (and COOKIE_SECURE=false for Safari)
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload --port 8080
```

Emails go to **Mailpit** in development: `docker compose up -d mailpit`, then
read them at http://localhost:8025.

## Configuration

`DATABASE_URL` is required; the rest have local-development defaults. See
`.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | `postgresql+psycopg://gateway:…@localhost:5432/authdb` |
| `APP_BASE_URL` | `http://localhost:5173` | Where links in emails point |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Origins allowed to send state-changing requests |
| `COOKIE_SECURE` | `true` | Must be true in production. `false` only for plain-HTTP local dev (Safari) |
| `EMAIL_BACKEND` | `console` | `resend` in production, `smtp` for Mailpit, `console` to log emails |
| `EMAIL_FROM` | `Construction Planner <no-reply@localhost>` | Sender; must be on a domain verified in Resend |
| `RESEND_API_KEY` | — | Needed when `EMAIL_BACKEND=resend` |
| `SMTP_HOST` / `SMTP_PORT` | `localhost` / `1025` | Mailpit |
| `C01_URL` … `C04_URL` | local dev ports above | Where each service listens |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Read timeout per proxied request (C01 can take minutes) |

In production, run uvicorn with `--proxy-headers --forwarded-allow-ips=<load
balancer>`, or rate limits will see every request as coming from the load
balancer.

## Docker

The compose Postgres needs `authdb` created once. Its data volume already
exists, so first-run scripts won't do it:

```bash
docker compose up -d postgres
docker compose exec -T postgres psql -U postgres -v gateway_password=gateway-local-only -f - < gateway/db/create_authdb.sql
```

(`gateway-local-only` is the compose default; if you set
`GATEWAY_DB_PASSWORD` in a root `.env`, use that instead.) Then
`docker compose up --build gateway mailpit`. The container runs
`alembic upgrade head` on every start, and reaches C01–C03 on the host via
`host.docker.internal`.

## Tests

```bash
.venv/bin/python -m pytest tests -v
```

The auth tests use the real Postgres from `DATABASE_URL`, but in a throwaway
schema (`pytest_…`) that the real migrations build and the run drops
afterwards. The fixture refuses to start unless every table exists in that
schema, so a test can never reach the data in `authdb`'s `public` schema.
