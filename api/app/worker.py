"""Background worker: (1) outbox relay, (2) webhook delivery with retries.

Run with:  python -m app.worker
Safe to run many replicas: rows are claimed with FOR UPDATE SKIP LOCKED.

Phase 5 will publish outbox events to Kafka in relay_outbox(); webhooks then become just
another consumer of the event stream.
"""

import json
import logging
import random
import signal
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import OutboxEvent, WebhookAttempt, WebhookDelivery, WebhookEndpoint
from .security import sign_payload

log = logging.getLogger("payforge.worker")

# Wait this long (seconds) after the Nth failed attempt, with +-10% jitter so a mass
# failure doesn't make every retry hit the merchant at the same instant.
BACKOFF_SCHEDULE = [10, 30, 120, 600, 3600]
LEASE_SECONDS = 120  # a claimed delivery isn't re-claimed for this long if the worker dies


def backoff_seconds(attempts_so_far: int, jitter: bool = True) -> float:
    base = BACKOFF_SCHEDULE[min(attempts_so_far, len(BACKOFF_SCHEDULE)) - 1]
    return base * random.uniform(0.9, 1.1) if jitter else float(base)


def relay_outbox(db: Session, batch_size: int | None = None) -> int:
    """Turn unprocessed outbox events into one delivery per subscribed endpoint."""
    batch = batch_size or get_settings().outbox_batch_size
    events = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .limit(batch)
        .with_for_update(skip_locked=True)
    ).all()
    now = datetime.now(UTC)
    for ev in events:
        endpoints = db.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.merchant_id == ev.merchant_id, WebhookEndpoint.active.is_(True)
            )
        ).all()
        for ep in endpoints:
            if "*" in ep.events or ev.type in ep.events:
                db.add(
                    WebhookDelivery(
                        merchant_id=ev.merchant_id,
                        endpoint_id=ep.id,
                        event_id=ev.id,
                        status="pending",
                        next_attempt_at=now,
                    )
                )
        ev.processed_at = now
    db.commit()
    return len(events)


def deliver_due(db: Session, client: httpx.Client) -> int:
    """Claim due deliveries (short lock), then call merchants outside any DB lock."""
    s = get_settings()
    now = datetime.now(UTC)
    due = db.scalars(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status.in_(("pending", "retrying")),
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(s.outbox_batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    ids = [d.id for d in due]
    for d in due:
        d.next_attempt_at = now + timedelta(seconds=LEASE_SECONDS)
    db.commit()
    for delivery_id in ids:
        _attempt(db, client, delivery_id)
    return len(ids)


def _attempt(db: Session, client: httpx.Client, delivery_id: str) -> None:
    s = get_settings()
    d = db.get(WebhookDelivery, delivery_id, populate_existing=True)
    endpoint = db.get(WebhookEndpoint, d.endpoint_id)
    event = db.get(OutboxEvent, d.event_id)
    attempt_no = d.attempts + 1

    status_code: int | None = None
    error: str | None = None
    started = time.perf_counter()

    if not endpoint.active:
        error = "endpoint_inactive"
        d.attempts = attempt_no
        d.status = "dead"
    else:
        body = json.dumps(event.payload, separators=(",", ":"), sort_keys=True).encode()
        headers = {
            "Content-Type": "application/json",
            "PayForge-Signature": sign_payload(endpoint.secret, int(time.time()), body),
            "PayForge-Event-Id": event.id,
            "PayForge-Delivery-Id": d.id,
        }
        try:
            resp = client.post(
                endpoint.url, content=body, headers=headers, timeout=s.webhook_timeout_seconds
            )
            status_code = resp.status_code
            if not 200 <= status_code < 300:
                error = f"HTTP {status_code}"
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]

        d.attempts = attempt_no
        if error is None:
            d.status = "succeeded"
        elif attempt_no >= s.webhook_max_attempts:
            d.status = "dead"  # dead-letter: stays visible and can be replayed via the API
        else:
            d.status = "retrying"
            d.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds(attempt_no))

    d.last_status_code = status_code
    d.last_error = error
    db.add(
        WebhookAttempt(
            delivery_id=d.id,
            attempt_no=attempt_no,
            response_status=status_code,
            error=error,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    )
    db.commit()


def run_forever() -> None:
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)  # graceful shutdown on `docker stop` / pod eviction
    signal.signal(signal.SIGINT, _stop)
    logging.basicConfig(level=logging.INFO)
    log.info("worker started")
    with httpx.Client() as client:
        while not stop:
            try:
                with SessionLocal() as db:
                    relayed = relay_outbox(db)
                    delivered = deliver_due(db, client)
                if not relayed and not delivered:
                    time.sleep(1)
            except Exception:
                log.exception("worker loop error")
                time.sleep(2)
    log.info("worker stopped")


if __name__ == "__main__":
    run_forever()
