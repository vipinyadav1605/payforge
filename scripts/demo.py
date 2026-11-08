"""End-to-end demo against a running PayForge (http://localhost:8000). Standard library only.

    python scripts/demo.py

Creates a merchant, takes a payment (twice, with the SAME idempotency key), refunds part of it,
and shows the balance, so you can watch idempotency and the ledger work.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
ADMIN_TOKEN = "dev-admin-token-change-me"


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), json.loads(err.read() or b"null")


def show(title, result):
    status, headers, body = result
    replayed = headers.get("Idempotent-Replayed")
    print(f"\n== {title}  [{status}]" + (f"  Idempotent-Replayed: {replayed}" if replayed else ""))
    print(json.dumps(body, indent=2))


def main():
    status, _, merchant = call("POST", "/admin/merchants",
                               {"name": "Demo Store", "email": "demo@example.com"},
                               {"X-Admin-Token": ADMIN_TOKEN})
    if status != 201:
        sys.exit(f"Could not create merchant ({status}). Is the API running and ADMIN_TOKEN correct?")
    auth = {"Authorization": f"Bearer {merchant['api_key']}"}
    print("merchant:", merchant["id"])

    payment = {"amount": 10_000, "currency": "usd", "payment_method": "pm_card_visa"}
    key = {"Idempotency-Key": "demo-order-1", **auth}
    first = call("POST", "/v1/payments", payment, key)
    show("create payment (first try)", first)
    show("create payment (RETRY, same key -> same payment, no double charge)",
         call("POST", "/v1/payments", payment, key))

    pid = first[2]["id"]
    show("refund 4000", call("POST", f"/v1/payments/{pid}/refunds", {"amount": 4000}, auth))
    show("declined card", call("POST", "/v1/payments",
                               {**payment, "payment_method": "pm_card_declined"}, auth))
    show("balance (ledger)", call("GET", "/v1/balance", headers=auth))


if __name__ == "__main__":
    main()
