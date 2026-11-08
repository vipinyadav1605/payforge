import json

import httpx
from sqlalchemy import select, text

from app.models import WebhookDelivery
from app.security import sign_payload, verify_signature
from app.worker import backoff_seconds, deliver_due, relay_outbox
from tests.conftest import pay


def _endpoint(client, headers, url="http://merchant.test/hook", **kw):
    r = client.post("/v1/webhook-endpoints", json={"url": url, **kw}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _make_due(db):
    db.execute(text("UPDATE webhook_deliveries SET next_attempt_at = now() - interval '1 second'"))
    db.commit()


def test_signature_roundtrip_and_tamper_detection():
    body = b'{"a":1}'
    header = sign_payload("whsec_x", 1_000_000, body)
    assert verify_signature("whsec_x", header, body, now=1_000_100)
    assert not verify_signature("whsec_x", header, b'{"a":2}', now=1_000_100)  # tampered body
    assert not verify_signature("whsec_other", header, body, now=1_000_100)  # wrong secret
    assert not verify_signature("whsec_x", header, body, now=1_009_999)  # too old (replay)
    assert not verify_signature("whsec_x", "garbage", body)


def test_secret_is_only_returned_at_creation(client, headers):
    created = _endpoint(client, headers)
    assert created["secret"].startswith("whsec_")
    assert client.get("/v1/webhook-endpoints", headers=headers).json()[0]["secret"] is None


def test_event_is_delivered_signed(client, headers, db):
    ep = _endpoint(client, headers)
    pay(client, headers, amount=10_000)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    assert relay_outbox(db) == 2  # payment.authorized + payment.captured
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert deliver_due(db, http) == 2

    assert {json.loads(r.content)["type"] for r in seen} == {"payment.authorized", "payment.captured"}
    for r in seen:
        assert verify_signature(ep["secret"], r.headers["PayForge-Signature"], r.content)
    assert {d.status for d in db.scalars(select(WebhookDelivery))} == {"succeeded"}


def test_event_filter_only_delivers_subscribed_types(client, headers, db):
    _endpoint(client, headers, events=["payment.captured"])
    pay(client, headers)
    relay_outbox(db)
    assert db.scalar(select(text("count(*)")).select_from(WebhookDelivery)) == 1


def test_failures_retry_then_dead_letter_then_replay(client, headers, db):
    _endpoint(client, headers, events=["payment.captured"])
    pay(client, headers)
    relay_outbox(db)
    calls = []

    def down(request):
        calls.append(1)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(down)) as http:
        for attempt in range(1, 7):
            _make_due(db)
            deliver_due(db, http)
            d = db.scalars(select(WebhookDelivery)).one()
            db.refresh(d)
            assert d.attempts == attempt
            assert d.status == ("dead" if attempt == 6 else "retrying")
    assert len(calls) == 6 and d.last_error == "HTTP 503"

    listing = client.get("/v1/webhook-deliveries?status=dead", headers=headers).json()["data"]
    assert len(listing) == 1 and len(listing[0]["attempt_log"]) == 6

    # The merchant fixes their server and replays the dead delivery.
    assert client.post(f"/v1/webhook-deliveries/{d.id}/replay", headers=headers).status_code == 200
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as http:
        deliver_due(db, http)
    db.refresh(d)
    assert d.status == "succeeded"


def test_network_errors_are_retried_not_crashed(client, headers, db):
    _endpoint(client, headers, events=["payment.captured"])
    pay(client, headers)
    relay_outbox(db)

    def boom(request):
        raise httpx.ConnectError("connection refused")

    with httpx.Client(transport=httpx.MockTransport(boom)) as http:
        deliver_due(db, http)
    d = db.scalars(select(WebhookDelivery)).one()
    assert d.status == "retrying" and "ConnectError" in d.last_error


def test_backoff_grows_and_is_capped():
    waits = [backoff_seconds(n, jitter=False) for n in range(1, 8)]
    assert waits == [10, 30, 120, 600, 3600, 3600, 3600]


def test_outbox_event_rolls_back_with_the_transaction(client, headers, db):
    """A rejected request must leave no phantom events behind (transactional outbox)."""
    p = pay(client, headers, capture=False).json()
    from app.models import OutboxEvent

    before = db.scalar(select(text("count(*)")).select_from(OutboxEvent))
    client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=headers)  # 409
    assert db.scalar(select(text("count(*)")).select_from(OutboxEvent)) == before
