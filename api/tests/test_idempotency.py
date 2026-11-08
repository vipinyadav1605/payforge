from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import LedgerTransaction, Payment

BODY = {"amount": 5_000, "currency": "usd", "payment_method": "pm_card_visa"}


def test_same_key_replays_response_without_charging_twice(client, headers, db):
    h = {**headers, "Idempotency-Key": "order-1001"}
    first = client.post("/v1/payments", json=BODY, headers=h)
    second = client.post("/v1/payments", json=BODY, headers=h)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert "Idempotent-Replayed" not in first.headers
    assert db.scalar(select(func.count()).select_from(Payment)) == 1
    assert db.scalar(select(func.count()).select_from(LedgerTransaction)) == 1
    assert client.get("/v1/balance", headers=headers).json()["available"] == {"usd": 4_875}


def test_same_key_different_body_is_rejected(client, headers):
    h = {**headers, "Idempotency-Key": "k-1"}
    client.post("/v1/payments", json=BODY, headers=h)
    r = client.post("/v1/payments", json={**BODY, "amount": 9_999}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "idempotency_key_reuse"


def test_keys_are_scoped_per_merchant(client, headers):
    from tests.conftest import make_merchant

    other = make_merchant(client, "Other")
    a = client.post("/v1/payments", json=BODY, headers={**headers, "Idempotency-Key": "same"})
    b = client.post("/v1/payments", json=BODY,
                    headers={"Authorization": f"Bearer {other['api_key']}", "Idempotency-Key": "same"})
    assert a.json()["id"] != b.json()["id"]


def test_failed_request_does_not_burn_the_key(client, headers):
    p = client.post("/v1/payments", json={**BODY, "capture": False}, headers=headers).json()
    h = {**headers, "Idempotency-Key": "refund-key"}
    # Refund before capture -> 409; the key must stay usable afterwards.
    assert client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=h).status_code == 409
    client.post(f"/v1/payments/{p['id']}/capture", headers=headers)
    assert client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=h).status_code == 201


def test_concurrent_requests_with_one_key_create_exactly_one_payment(headers, db):
    h = {**headers, "Idempotency-Key": "race-key"}

    def call(_):
        with TestClient(app) as c:
            return c.post("/v1/payments", json=BODY, headers=h)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(8)))

    assert {r.status_code for r in results} == {201}
    assert len({r.json()["id"] for r in results}) == 1
    assert db.scalar(select(func.count()).select_from(Payment)) == 1
    assert db.scalar(select(func.count()).select_from(LedgerTransaction)) == 1
