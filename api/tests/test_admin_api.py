from sqlalchemy import select

from app.models import WebhookDelivery
from app.worker import relay_outbox
from tests.conftest import ADMIN, pay


def test_suspended_merchant_cannot_use_the_api_until_reactivated(client, merchant, headers):
    assert client.get("/v1/me", headers=headers).status_code == 200

    r = client.patch(f"/admin/merchants/{merchant['id']}", json={"status": "suspended"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    blocked = client.get("/v1/me", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "merchant_inactive"

    client.patch(f"/admin/merchants/{merchant['id']}", json={"status": "active"}, headers=ADMIN)
    assert client.get("/v1/me", headers=headers).status_code == 200


def test_admin_endpoints_require_the_admin_token(client, merchant):
    assert client.patch(f"/admin/merchants/{merchant['id']}", json={"status": "suspended"}).status_code == 401
    assert client.post("/admin/webhook-deliveries/whd_x/replay").status_code == 401


def test_invalid_status_and_unknown_ids(client):
    assert client.patch("/admin/merchants/mer_nope", json={"status": "active"}, headers=ADMIN).status_code == 404
    assert client.patch("/admin/merchants/mer_nope", json={"status": "banana"}, headers=ADMIN).status_code == 422
    assert client.post("/admin/webhook-deliveries/whd_nope/replay", headers=ADMIN).status_code == 404


def test_admin_can_replay_a_dead_delivery_of_any_merchant(client, headers, db):
    client.post("/v1/webhook-endpoints", json={"url": "http://merchant.test/h", "events": ["payment.captured"]},
                headers=headers)
    pay(client, headers)
    relay_outbox(db)
    delivery = db.scalars(select(WebhookDelivery)).one()
    delivery.status, delivery.attempts = "dead", 6
    db.commit()

    r = client.post(f"/admin/webhook-deliveries/{delivery.id}/replay", headers=ADMIN)
    assert r.status_code == 200
    db.refresh(delivery)
    assert delivery.status == "pending" and delivery.attempts == 0
