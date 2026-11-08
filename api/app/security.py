import hashlib
import hmac
import secrets
import time


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, sha256_hash). Store only the hash."""
    raw = "pf_test_" + secrets.token_urlsafe(32)
    return raw, hash_key(raw)


def generate_webhook_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    """Signature header value: t=<unix ts>,v1=<hex hmac-sha256 of '<ts>.<body>'>.
    Signing the timestamp too lets receivers reject replayed (old) deliveries."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify_signature(
    secret: str, header: str, body: bytes, tolerance_seconds: int = 300, now: float | None = None
) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs((now if now is not None else time.time()) - ts) > tolerance_seconds:
        return False
    expected = sign_payload(secret, ts, body).split("v1=")[1]
    return hmac.compare_digest(expected, given)
