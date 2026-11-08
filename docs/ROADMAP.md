# Roadmap and learning plan

Each phase ends with something shippable, a measurement, and a short entry in
[LEARNING_LOG.md](LEARNING_LOG.md). Tick boxes as you go.

## Phase 1 - Foundation  (DONE in this scaffold: read the code, then re-type parts of it)
- [x] FastAPI app, SQLAlchemy 2, Alembic migrations, API keys, tests
- [ ] **You:** read `models.py` -> `services/payments.py` -> `routers/payments.py` in that order
- [ ] **You:** add one small feature yourself (e.g. `GET /v1/refunds/{id}`) with a test

## Phase 2 - Payments depth
- [x] Idempotency, state machine, ledger with DB constraints, signed webhooks
- [ ] Two-phase PSP call (`pending` commit -> PSP call -> result transaction) + reconcile "unknown" outcomes
- [ ] Razorpay or Stripe **test mode** adapter behind `psp.authorize`
- [ ] Payouts: move merchant balance out via a ledger transaction
- [ ] Learn: ACID, isolation levels, `SELECT ... FOR UPDATE`, why floats are banned for money

## Phase 3 - Docker + CI/CD
- [x] Dockerfile, docker-compose, GitHub Actions (lint + tests + image build)
- [ ] Multi-stage build, non-root image, `.dockerignore`, smaller image; add Trivy scan to CI
- [ ] Push image to GitHub Container Registry; semantic version tags

## Phase 4 - Performance
- [x] Connection pool settings, rate limiter
- [ ] Load test with **k6** (baseline: create-payment p50/p95/p99, error rate)
- [ ] `EXPLAIN ANALYZE` the slow queries; add/remove indexes; measure again
- [ ] PgBouncer in front of Postgres; compare pool sizes
- [ ] Redis caching for API-key lookups; idempotency-key cleanup job
- [ ] Learn: pooling, indexes, N+1, caching and invalidation, rate-limit algorithms

## Phase 5 - Event-driven (Kafka)
- [ ] Kafka (Strimzi on k8s, or docker compose locally); outbox relay publishes to a topic
- [ ] Webhook delivery becomes a Kafka consumer; idempotent consumers; DLQ topic
- [ ] Split `webhooks`/`ledger` into their own services if you can justify it
- [ ] Learn: partitions, consumer groups, ordering by key, delivery semantics

## Phase 6 - Kubernetes + cloud
- [ ] Local cluster (kind/minikube): Deployments, Services, Ingress, ConfigMap, Secret
- [ ] Probes (`/health/live`, `/health/ready`), resource requests/limits, HPA, PodDisruptionBudget
- [ ] Helm chart; k3s on a free cloud VM (check current free-tier terms); TLS with cert-manager
- [ ] Terraform for the cloud resources

## Phase 7 - Reliability and security
- [ ] Prometheus + Grafana dashboards (metrics already exposed at `/metrics`), alerts on SLOs
- [ ] OpenTelemetry tracing across api -> worker
- [ ] Chaos tests: kill pods/DB mid-payment; prove the ledger still balances and nothing is lost
- [ ] Encrypt webhook secrets, rotate API keys, audit log in MongoDB, dependency scanning

## Resume milestones
- After phase 2+3: "idempotent payments API with double-entry ledger, CI/CD, Dockerized"
- After phase 4: add real numbers ("sustained N req/s, p99 X ms")
- After phase 6: "deployed on Kubernetes with autoscaling and monitoring"
