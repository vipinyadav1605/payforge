import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import ledger
from tests.conftest import pay


def test_refund_math_and_balance(client, headers, db):
    p = pay(client, headers, amount=10_000).json()  # fee 250, merchant net 9750
    r = client.post(f"/v1/payments/{p['id']}/refunds", json={"amount": 4_000}, headers=headers)
    assert r.status_code == 201
    assert r.json()["fee_refunded"] == 100  # 250 * 4000/10000
    got = client.get(f"/v1/payments/{p['id']}", headers=headers).json()
    assert got["status"] == "partially_refunded" and got["amount_refunded"] == 4_000
    # merchant keeps 9750 - (4000 - 100) = 5850
    assert client.get("/v1/balance", headers=headers).json()["available"] == {"usd": 5_850}

    client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=headers)  # rest: 6000
    got = client.get(f"/v1/payments/{p['id']}", headers=headers).json()
    assert got["status"] == "refunded" and got["amount_refunded"] == 10_000
    assert client.get("/v1/balance", headers=headers).json()["available"] == {"usd": 0}
    ledger.assert_all_balanced(db)


def test_cannot_refund_more_than_captured(client, headers):
    p = pay(client, headers, amount=1_000).json()
    r = client.post(f"/v1/payments/{p['id']}/refunds", json={"amount": 1_001}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "refund_exceeds_payment"
    client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=headers)
    assert client.post(f"/v1/payments/{p['id']}/refunds", json={}, headers=headers).status_code == 409


def test_every_ledger_transaction_balances(client, headers, db):
    for amount in (101, 999, 12_345, 7):  # odd amounts exercise fee rounding
        p = pay(client, headers, amount=amount).json()
        client.post(f"/v1/payments/{p['id']}/refunds", json={"amount": max(1, amount // 3)}, headers=headers)
    ledger.assert_all_balanced(db)


def test_database_rejects_an_unbalanced_ledger_transaction(db):
    acc = ledger.get_or_create_account(db, "platform", "clearing", "usd")
    db.execute(text("INSERT INTO ledger_transactions (id, ref_type, ref_id, created_at) "
                    "VALUES ('ltx_bad','test','x', now())"))
    db.execute(text("INSERT INTO ledger_entries (transaction_id, account_id, direction, amount, created_at) "
                    f"VALUES ('ltx_bad', '{acc.id}', 'debit', 100, now())"))
    with pytest.raises(DBAPIError, match="unbalanced"):
        db.commit()  # the DEFERRED constraint trigger fires at commit
    db.rollback()


def test_ledger_entries_are_append_only(client, headers, db):
    pay(client, headers)
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE ledger_entries SET amount = amount + 1"))
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM ledger_entries"))
    db.rollback()


def test_each_event_is_posted_to_the_ledger_once(client, headers, db):
    p = pay(client, headers).json()
    from app.models import Payment

    payment = db.get(Payment, p["id"])
    with pytest.raises(Exception, match="uq_ledger_tx_ref"):
        ledger.record_capture(db, payment)  # a second capture posting violates the unique ref
    db.rollback()
