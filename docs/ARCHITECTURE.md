# Architecture

```
 Merchant ──HTTPS──► API (FastAPI)                         Worker (python -m app.worker)
                      │ auth → rate limit (Redis)           │ 1. relay: outbox → deliveries
                      │ idempotency check                   │ 2. deliver: signed POST + retries
                      ▼                                     ▼
                  PostgreSQL  ◄───────── same database ────────┘
        payments · ledger_* · idempotency_keys · outbox_events · webhook_*
```

Today this is a **modular monolith** (one codebase, two processes: `api` and `worker`). That is
deliberate: split into services once you can say *why* (see ROADMAP phase 5).

## One payment, in one database transaction

`POST /v1/payments` runs inside a single DB transaction that contains:
1. the idempotency-key row,
2. the payment row (state machine `created → authorized → captured`),
3. the double-entry ledger transaction (`DR clearing / CR merchant balance / CR fees`),
4. outbox events (`payment.authorized`, `payment.captured`).

Either **all** of it commits or **none** of it does. A crash at any point cannot leave money
moved without a ledger entry, or an event announced for a payment that rolled back.

## Key design decisions

| Decision | Why | Trade-off |
|---|---|---|
| Money = integer minor units | floats can't represent cents exactly | must format for display |
| Double-entry ledger, **append-only**, DB-enforced balance | balances are derived and auditable; bugs can't silently create money | queries sum entries (cache/snapshot later) |
| Idempotency row inside the business transaction | concurrent duplicates serialize on the unique index; failures never burn the key | key row exists only if the work committed |
| Transactional outbox | DB write + event can't diverge (no dual-write problem) | events are delivered *at least once*, so consumers must dedupe (`PayForge-Event-Id`) |
| Webhooks: HMAC over `timestamp.body` | receivers can verify origin and reject replays | merchants must implement verification |
| Retries: 10s, 30s, 2m, 10m, 1h + jitter, then dead-letter | protects merchants' servers; nothing is silently dropped | max ~1h10m before dead; replay via API |
| `FOR UPDATE SKIP LOCKED` queue claims | many workers, no double-processing, no blocking | a crashed worker's rows come back after the 120s lease |
| Token bucket in Redis Lua, **fail-open** | atomic across replicas; Redis outage must not stop payments | brief unlimited window during an outage |
| Row lock (`FOR UPDATE`) on capture/refund/cancel | two concurrent refunds can't exceed the captured amount | per-payment serialization |
| Django back-office reads the DB, **writes only via the API** | one writer means one place for rules, validation and audit; staff can't corrupt the ledger | an extra HTTP hop for staff actions; the API needs `/admin/*` endpoints |

## Known simplifications (be ready to discuss these in interviews)

1. **The mock PSP is called inside the DB transaction.** With a real PSP you must not hold a
   transaction (and row locks) open during a slow network call. The production pattern is:
   commit a `pending` payment first, call the PSP with *its* idempotency key, then record the
   result in a second transaction, with a reconciliation job to resolve unknown outcomes.
   (Roadmap phase 2.)
2. Webhook secrets are stored in plaintext (encrypt at rest / use a KMS: phase 7).
3. Idempotency keys are never pruned yet (needs a 24h cleanup job: phase 4).
4. One currency per ledger account, no FX; no payouts yet (merchant balance only grows).
5. No tenant-level API key rotation endpoint yet.
