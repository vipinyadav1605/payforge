from tests.conftest import make_merchant, pay


def test_successful_payment_is_captured_with_fee_and_balance(client, headers):
    r = pay(client, headers, amount=10_000)
    assert r.status_code == 201
    p = r.json()
    assert p["status"] == "captured"
    assert p["amount_captured"] == 10_000
    assert p["fee_amount"] == 250  # 2.5%
    assert client.get("/v1/balance", headers=headers).json()["available"] == {"usd": 9_750}


def test_declined_payment_fails_and_moves_no_money(client, headers):
    p = pay(client, headers, method="pm_card_declined").json()
    assert p["status"] == "failed"
    assert p["failure_code"] == "card_declined"
    assert client.get("/v1/balance", headers=headers).json()["available"] == {}


def test_authorize_then_capture(client, headers):
    p = pay(client, headers, capture=False).json()
    assert p["status"] == "authorized"
    assert client.get("/v1/balance", headers=headers).json()["available"] == {}
    c = client.post(f"/v1/payments/{p['id']}/capture", headers=headers)
    assert c.status_code == 200 and c.json()["status"] == "captured"
    assert client.get("/v1/balance", headers=headers).json()["available"] == {"usd": 9_750}


def test_cannot_capture_twice_or_capture_a_failed_payment(client, headers):
    p = pay(client, headers).json()
    assert client.post(f"/v1/payments/{p['id']}/capture", headers=headers).status_code == 409
    failed = pay(client, headers, method="pm_card_declined").json()
    assert client.post(f"/v1/payments/{failed['id']}/capture", headers=headers).status_code == 409


def test_cancel_authorized_payment(client, headers):
    p = pay(client, headers, capture=False).json()
    r = client.post(f"/v1/payments/{p['id']}/cancel", headers=headers)
    assert r.json()["status"] == "canceled"
    assert client.post(f"/v1/payments/{p['id']}/capture", headers=headers).status_code == 409


def test_merchants_cannot_see_each_others_payments(client, headers):
    p = pay(client, headers).json()
    other = make_merchant(client, "Other")
    other_headers = {"Authorization": f"Bearer {other['api_key']}"}
    assert client.get(f"/v1/payments/{p['id']}", headers=other_headers).status_code == 404
    assert client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=other_headers).status_code == 404
    assert client.get("/v1/payments", headers=other_headers).json()["data"] == []


def test_cursor_pagination(client, headers):
    ids = [pay(client, headers, amount=100 + i).json()["id"] for i in range(5)]
    first = client.get("/v1/payments?limit=2", headers=headers).json()
    assert [p["id"] for p in first["data"]] == ids[::-1][:2] and first["has_more"] is True
    second = client.get(f"/v1/payments?limit=2&starting_after={first['data'][-1]['id']}",
                        headers=headers).json()
    assert [p["id"] for p in second["data"]] == ids[::-1][2:4] and second["has_more"] is True
    last = client.get(f"/v1/payments?limit=2&starting_after={second['data'][-1]['id']}",
                      headers=headers).json()
    assert [p["id"] for p in last["data"]] == ids[::-1][4:] and last["has_more"] is False


def test_metadata_and_description_round_trip(client, headers):
    p = pay(client, headers, description="order 42", metadata={"order_id": "42"}).json()
    got = client.get(f"/v1/payments/{p['id']}", headers=headers).json()
    assert got["description"] == "order 42" and got["metadata"] == {"order_id": "42"}
