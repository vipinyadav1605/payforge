"""Idempotency keys: a retried request with the same Idempotency-Key never executes twice.

How it stays correct under concurrency
--------------------------------------
The key row is INSERTed (ON CONFLICT DO NOTHING) inside the SAME database transaction that
does the business work, and the stored response is written before COMMIT.
  * Two concurrent requests with one key: the second INSERT blocks on the unique index until
    the first transaction commits, then conflicts, then replays the stored response.
  * If the handler fails, the whole transaction (including the key row) rolls back, so the
    client may safely retry.
  * Same key + different request body  ->  422 (a client bug, not a retry).
Keys should be pruned after ~24h by a cleanup job (Phase 4).
"""

import hashlib
import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .errors import ApiError
from .models import IdempotencyKey


def fingerprint(method: str, path: str, body: dict[str, Any] | None) -> str:
    canonical = json.dumps(
        {"m": method, "p": path, "b": body}, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def run_idempotent(
    db: Session,
    merchant_id: str,
    key: str | None,
    request_hash: str,
    handler: Callable[[], tuple[int, dict[str, Any]]],
) -> tuple[int, dict[str, Any], bool]:
    """Runs handler() at most once per (merchant, key). Returns (status, body, replayed)."""
    if key is None:
        status, body = handler()
        db.commit()
        return status, body, False

    if len(key) > 255:
        raise ApiError(422, "invalid_idempotency_key", "Idempotency-Key must be <= 255 characters.")

    inserted = db.execute(
        pg_insert(IdempotencyKey)
        .values(merchant_id=merchant_id, key=key, request_hash=request_hash)
        .on_conflict_do_nothing(constraint="uq_idempotency_merchant_key")
        .returning(IdempotencyKey.id)
    ).first()

    if inserted is None:  # the key already exists (committed by an earlier/concurrent request)
        existing = db.scalars(
            select(IdempotencyKey).where(
                IdempotencyKey.merchant_id == merchant_id, IdempotencyKey.key == key
            )
        ).one()
        if existing.request_hash != request_hash:
            raise ApiError(
                422,
                "idempotency_key_reuse",
                "This Idempotency-Key was already used with a different request.",
            )
        return existing.response_code or 200, existing.response_body or {}, True

    status, body = handler()
    db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.id == inserted[0])
        .values(response_code=status, response_body=body)
    )
    db.commit()
    return status, body, False
