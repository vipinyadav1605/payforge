from tests.conftest import ADMIN, make_merchant


def test_liveness_and_readiness(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200


def test_metrics_endpoint(client):
    client.get("/health/live")
    assert b"payforge_http_requests_total" in client.get("/metrics/").content


def test_missing_and_bad_api_key(client):
    assert client.get("/v1/me").status_code == 401
    r = client.get("/v1/me", headers={"Authorization": "Bearer pf_test_nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_api_key"


def test_admin_endpoint_requires_token(client):
    r = client.post("/admin/merchants", json={"name": "x", "email": "x@x.com"})
    assert r.status_code == 401
    r = client.post("/admin/merchants", json={"name": "x", "email": "x@x.com"},
                    headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401
    assert client.post("/admin/merchants", json={"name": "x", "email": "x@x.com"},
                       headers=ADMIN).status_code == 201


def test_api_key_is_stored_hashed(client, db):
    from sqlalchemy import select

    from app.models import ApiKey

    m = make_merchant(client)
    stored = db.scalars(select(ApiKey)).one()
    assert stored.key_hash != m["api_key"]
    assert m["api_key"] not in (stored.prefix, stored.key_hash)


def test_validation_errors_use_the_error_envelope(client, headers):
    r = client.post("/v1/payments", headers=headers,
                    json={"amount": -5, "currency": "xyz", "payment_method": "pm_card_visa"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert {d["field"] for d in body["details"]} == {"amount", "currency"}
