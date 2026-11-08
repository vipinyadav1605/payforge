import math
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ratelimit
from .config import get_settings
from .db import get_db
from .errors import ApiError
from .models import ApiKey, Merchant
from .security import hash_key

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    merchant: Merchant
    api_key: ApiKey


def get_auth(
    response: Response,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise ApiError(401, "authentication_required", "Send your API key as 'Authorization: Bearer <key>'.")
    api_key = db.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_key(creds.credentials), ApiKey.revoked_at.is_(None))
    )
    if api_key is None:
        raise ApiError(401, "invalid_api_key", "The API key is invalid or has been revoked.")
    merchant = db.get(Merchant, api_key.merchant_id)
    if merchant is None or merchant.status != "active":
        raise ApiError(403, "merchant_inactive", "This merchant account is not active.")

    s = get_settings()
    if s.rate_limit_enabled:
        result = ratelimit.check(api_key.id, s.rate_limit_capacity, s.rate_limit_refill_per_sec)
        if result is not None:
            response.headers["X-RateLimit-Limit"] = str(s.rate_limit_capacity)
            response.headers["X-RateLimit-Remaining"] = str(int(result.remaining))
            if not result.allowed:
                retry = max(1, math.ceil(result.retry_after))
                raise ApiError(
                    429,
                    "rate_limited",
                    "Too many requests. Slow down and retry.",
                    headers={"Retry-After": str(retry), "X-RateLimit-Remaining": "0"},
                )
    return AuthContext(merchant=merchant, api_key=api_key)


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_token
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise ApiError(401, "invalid_admin_token", "Missing or invalid X-Admin-Token.")
