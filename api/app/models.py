from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .ids import new_id

TS = DateTime(timezone=True)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _pk(prefix: str):
    return mapped_column(String(40), primary_key=True, default=lambda: new_id(prefix))


class Merchant(Base):
    __tablename__ = "merchants"
    id: Mapped[str] = _pk("mer")
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)


class ApiKey(Base):
    """Only a SHA-256 hash of the key is stored; the raw key is shown once."""

    __tablename__ = "api_keys"
    id: Mapped[str] = _pk("key")
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(TS, nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = _pk("pay")
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    # Money is ALWAYS an integer in the smallest currency unit (cents/paise). Never float.
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24))
    payment_method: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    psp_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount_captured: Mapped[int] = mapped_column(BigInteger, default=0)
    amount_refunded: Mapped[int] = mapped_column(BigInteger, default=0)
    fee_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    fee_refunded: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint("amount_captured <= amount", name="ck_payments_captured_le_amount"),
        CheckConstraint("amount_refunded <= amount_captured", name="ck_payments_refund_le_captured"),
        Index("ix_payments_merchant_created", "merchant_id", "created_at", "id"),
    )


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[str] = _pk("re")
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    fee_refunded: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(20), default="succeeded")
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),)


# ---------------------------------------------------------------- ledger ----
class LedgerAccount(Base):
    """owner_id is a merchant id, or the literal 'platform' for PayForge's own accounts."""

    __tablename__ = "ledger_accounts"
    id: Mapped[str] = _pk("acc")
    owner_id: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    __table_args__ = (UniqueConstraint("owner_id", "code", "currency", name="uq_ledger_account"),)


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    id: Mapped[str] = _pk("ltx")
    merchant_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_type: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    # Each business event can be posted to the ledger exactly once.
    __table_args__ = (UniqueConstraint("ref_type", "ref_id", name="uq_ledger_tx_ref"),)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("ledger_transactions.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)
    direction: Mapped[str] = mapped_column(String(6))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    __table_args__ = (
        CheckConstraint("direction in ('debit','credit')", name="ck_entry_direction"),
        CheckConstraint("amount > 0", name="ck_entry_amount_positive"),
    )


# ----------------------------------------------------------- idempotency ----
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    __table_args__ = (UniqueConstraint("merchant_id", "key", name="uq_idempotency_merchant_key"),)


# ------------------------------------------------------ outbox + webhooks ----
class OutboxEvent(Base):
    """Written in the SAME transaction as the business change (transactional outbox).
    A relay turns each row into deliveries (and, in a later phase, Kafka messages)."""

    __tablename__ = "outbox_events"
    id: Mapped[str] = _pk("evt")
    merchant_id: Mapped[str] = mapped_column(String(40))
    type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    processed_at: Mapped[dt.datetime | None] = mapped_column(TS, nullable=True)

    __table_args__ = (
        Index(
            "ix_outbox_unprocessed",
            "created_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    id: Mapped[str] = _pk("we")
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(String(100))  # TODO(phase 7): encrypt at rest
    events: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["*"])
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = _pk("whd")
    merchant_id: Mapped[str] = mapped_column(String(40), index=True)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id"))
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|retrying|succeeded|dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_deliveries_due", "status", "next_attempt_at"),)


class WebhookAttempt(Base):
    __tablename__ = "webhook_attempts"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(ForeignKey("webhook_deliveries.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
