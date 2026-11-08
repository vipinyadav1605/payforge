"""A tiny merchant-side webhook receiver that VERIFIES PayForge signatures. Standard library only.

    python scripts/webhook_receiver.py whsec_<your endpoint secret>

Register http://host.docker.internal:9000/hook as a webhook endpoint (the worker runs inside
Docker, so 'localhost' would point at the container itself), then make a payment.
Set FAIL=1 to answer 500 so you can watch PayForge retry with backoff.
"""

import hashlib
import hmac
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = sys.argv[1] if len(sys.argv) > 1 else "whsec_replace_me"


def verify(header: str, body: bytes, tolerance: int = 300) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, given = int(parts["t"]), parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        ok = verify(self.headers.get("PayForge-Signature", ""), body)
        print(f"{'VALID  ' if ok else 'INVALID'} {self.headers.get('PayForge-Event-Id')} {body[:120]!r}")
        code = 400 if not ok else (500 if os.environ.get("FAIL") else 200)
        self.send_response(code)
        self.end_headers()

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print("listening on :9000")
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
