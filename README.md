# PayForge

A multi-tenant **payment platform** (a miniature Stripe/Razorpay): idempotent payments API, a
double-entry ledger, transactional outbox, and reliable signed webhooks. Built to learn and
demonstrate production backend engineering: correctness under failure, Docker, Kubernetes,
CI/CD, observability.

> Status: **Phase 1-2 core** (this commit). See [docs/ROADMAP.md](docs/ROADMAP.md) for what's next.

## What works today

| Feature | Where |
|---|---|
| Merchant onboarding, hashed API keys (`Bearer pf_test_...`) | `app/routers/admin.py`, `app/deps.py` |
| Payments: create, authorize, capture, cancel, list (cursor pagination) | `app/services/payments.py` |
| Payment **state machine** with illegal transitions rejected | `TRANSITIONS` in `services/payments.py` |
| Refunds (partial/full) with exact integer fee-refund maths | `refund_payment` |
| **Idempotency keys**, safe under concurrent retries | `app/idempotency.py` |
| **Double-entry ledger** + DB triggers (must balance, append-only) | `app/ledger.py`, migration `0001` |
| **Transactional outbox** (events can't be lost or phantom) | `app/outbox.py` |
| **Signed webhooks**, retries with backoff + jitter, dead-letter, replay | `app/worker.py` |
| Distributed **rate limiter** (Redis token bucket in Lua, fails open) | `app/ratelimit.py` |
| SSRF guard for webhook URLs, health probes, Prometheus `/metrics`, JSON logs | `urlcheck.py`, `main.py` |
| Test suite (real Postgres + Redis), CI workflow | `api/tests`, `.github/workflows/ci.yml` |

## Quick start (Windows PowerShell)

Requires Docker Desktop (running). No Python needed on your machine.

```powershell
.\dev.ps1 up          # builds + starts Postgres, Redis, API, worker (migrations run automatically)
.\dev.ps1 test        # runs the test suite in a container
python scripts/demo.py   # watch idempotency + the ledger work (needs the stack running)
```

Open the **merchant dashboard** at <http://localhost:5173> (click "Create merchant and sign in";
it has payments, a "send twice with the same Idempotency-Key" demo, refunds and webhooks with
live delivery status) and the interactive API docs at <http://localhost:8000/docs>. `.\dev.ps1` lists every command
(`logs`, `psql`, `cov`, `lint`, `migrate`, `revision "msg"`, `reset`).

## Using the API

```powershell
# 1. Onboard a merchant (admin token is in .env). The API key is shown ONCE.
curl.exe -s -X POST localhost:8000/admin/merchants -H "X-Admin-Token: dev-admin-token-change-me" `
  -H "Content-Type: application/json" -d '{\"name\":\"Acme\",\"email\":\"a@acme.test\"}'

# 2. Take a payment. Retrying with the same Idempotency-Key never charges twice.
curl.exe -s -X POST localhost:8000/v1/payments -H "Authorization: Bearer <api_key>" `
  -H "Idempotency-Key: order-1001" -H "Content-Type: application/json" `
  -d '{\"amount\":10000,\"currency\":\"usd\",\"payment_method\":\"pm_card_visa\"}'
```

Test payment methods (mock PSP): `pm_card_visa` (approved), `pm_card_declined`,
`pm_card_insufficient_funds`, `pm_card_expired`. Amounts are integers in the smallest unit
(10000 = $100.00).

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/payments` | `capture: false` = authorize only. Idempotency-Key supported |
| GET | `/v1/payments`, `/v1/payments/{id}` | `?limit=&starting_after=` cursor pagination |
| POST | `/v1/payments/{id}/capture` \| `/cancel` \| `/refunds` | state-machine guarded |
| GET | `/v1/balance`, `/v1/me` | balance comes from the ledger |
| POST/GET/DELETE | `/v1/webhook-endpoints` | secret returned once |
| GET / POST | `/v1/webhook-deliveries`, `.../{id}/replay` | delivery log, dead-letter replay |
| GET | `/health/live`, `/health/ready`, `/metrics` | probes + Prometheus |

Try webhooks end to end: run `python scripts/webhook_receiver.py <secret>`, register
`http://host.docker.internal:9000/hook` as an endpoint, make a payment, and watch signed events
arrive. Run it with `$env:FAIL=1` to watch retries and backoff.

## Project layout

```
payforge/
  docker-compose.yml     db + redis + api + worker + web
  web/                   React (Vite) merchant dashboard; /api/* is proxied to the API
  dev.ps1                shortcuts (up, test, migrate, ...)
  api/
    app/                 main.py, models.py, ledger.py, idempotency.py, outbox.py,
                         ratelimit.py, worker.py, services/, routers/
    migrations/          Alembic (includes the ledger safety triggers)
    tests/               pytest against a real Postgres + Redis
  docs/                  PROJECT_PLAN.md (master plan), ARCHITECTURE.md, ROADMAP.md, LEARNING_LOG.md
  scripts/               demo.py, webhook_receiver.py
```

## Run tests without Docker Compose (optional)

Point at any Postgres 16 and Redis, then: `cd api; pip install -r requirements.txt -r requirements-dev.txt; pytest`
(`DATABASE_URL` / `REDIS_URL` env vars; tests use their own `payforge_test` database).

## License

MIT (add a LICENSE file before publishing).
