"""Payment business logic. Functions here never commit: the caller (run_idempotent)
commits once, so the payment, ledger entries, outbox events and idempotency record
all succeed or fail together."""

from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .. import ledger, outbox, psp
from ..config import get_settings
from ..errors import ApiError
from ..models import Merchant, Payment, Refund
from ..schemas import PaymentCreate, RefundCreate

# The payment state machine: status -> statuses it may move to.
TRANSITIONS: dict[str, set[str]] = {
    "created": {"authorized", "failed"},
    "authorized": {"captured", "canceled"},
    "captured": {"partially_refunded", "refunded"},
    "partially_refunded": {"partially_refunded", "refunded"},
    "failed": set(),
    "canceled": set(),
    "refunded": set(),
}


def transition(payment: Payment, new_status: str) -> None:
    if new_status not in TRANSITIONS.get(payment.status, set()):
        raise ApiError(
            409,
            "invalid_state",
            f"Payment is '{payment.status}' and cannot move to '{new_status}'.",
        )
    payment.status = new_status


def compute_fee(amount: int) -> int:
    bps = get_settings().platform_fee_bps
    return (amount * bps + 5000) // 10000  # integer math, rounded half up


def serialize_payment(p: Payment) -> dict[str, Any]:
    return {
        "id": p.id,
        "object": "payment",
        "amount": p.amount,
        "currency": p.currency,
        "status": p.status,
        "payment_method": p.payment_method,
        "description": p.description,
        "metadata": p.metadata_ or {},
        "amount_captured": p.amount_captured,
        "amount_refunded": p.amount_refunded,
        "fee_amount": p.fee_amount,
        "failure_code": p.failure_code,
        "created": int(p.created_at.timestamp()),
    }


def serialize_refund(r: Refund) -> dict[str, Any]:
    return {
        "id": r.id,
        "object": "refund",
        "payment_id": r.payment_id,
        "amount": r.amount,
        "fee_refunded": r.fee_refunded,
        "status": r.status,
        "reason": r.reason,
        "created": int(r.created_at.timestamp()),
    }


def get_payment(db: Session, merchant_id: str, payment_id: str, lock: bool = False) -> Payment:
    stmt = select(Payment).where(Payment.id == payment_id, Payment.merchant_id == merchant_id)
    if lock:
        # Row lock: serializes concurrent capture/refund/cancel on the same payment.
        stmt = stmt.with_for_update()
    payment = db.scalars(stmt).one_or_none()
    if payment is None:  # also hides other merchants' payments (no cross-tenant leaks)
        raise ApiError(404, "payment_not_found", f"No such payment: {payment_id}")
    return payment


def create_payment(db: Session, merchant: Merchant, data: PaymentCreate) -> dict[str, Any]:
    payment = Payment(
        merchant_id=merchant.id,
        amount=data.amount,
        currency=data.currency,
        status="created",
        payment_method=data.payment_method,
        description=data.description,
        metadata_=data.metadata,
    )
    db.add(payment)
    db.flush()

    result = psp.authorize(data.payment_method, data.amount, data.currency)
    payment.psp_reference = result.reference
    if not result.approved:
        payment.failure_code = result.failure_code
        transition(payment, "failed")
        outbox.emit(db, merchant.id, "payment.failed", serialize_payment(payment))
    else:
        transition(payment, "authorized")
        outbox.emit(db, merchant.id, "payment.authorized", serialize_payment(payment))
        if data.capture:
            _capture(db, payment)
    db.flush()
    return serialize_payment(payment)


def _capture(db: Session, payment: Payment) -> None:
    transition(payment, "captured")
    payment.amount_captured = payment.amount
    payment.fee_amount = compute_fee(payment.amount)
    ledger.record_capture(db, payment)
    outbox.emit(db, payment.merchant_id, "payment.captured", serialize_payment(payment))


def capture_payment(db: Session, merchant: Merchant, payment_id: str) -> dict[str, Any]:
    payment = get_payment(db, merchant.id, payment_id, lock=True)
    _capture(db, payment)
    db.flush()
    return serialize_payment(payment)


def cancel_payment(db: Session, merchant: Merchant, payment_id: str) -> dict[str, Any]:
    payment = get_payment(db, merchant.id, payment_id, lock=True)
    transition(payment, "canceled")
    outbox.emit(db, merchant.id, "payment.canceled", serialize_payment(payment))
    db.flush()
    return serialize_payment(payment)


def refund_payment(
    db: Session, merchant: Merchant, payment_id: str, data: RefundCreate
) -> dict[str, Any]:
    payment = get_payment(db, merchant.id, payment_id, lock=True)
    if payment.status not in ("captured", "partially_refunded"):
        raise ApiError(409, "invalid_state", f"Cannot refund a payment that is '{payment.status}'.")

    remaining = payment.amount_captured - payment.amount_refunded
    amount = data.amount if data.amount is not None else remaining
    if amount > remaining:
        raise ApiError(
            422, "refund_exceeds_payment", f"Only {remaining} is left to refund on this payment."
        )

    refunded_after = payment.amount_refunded + amount
    # Give back the platform fee proportionally, using exact integer rounding (half up).
    fee_refunded_after = (
        payment.fee_amount * refunded_after * 2 + payment.amount_captured
    ) // (2 * payment.amount_captured)
    fee_refund = fee_refunded_after - payment.fee_refunded

    refund = Refund(
        payment_id=payment.id,
        merchant_id=merchant.id,
        amount=amount,
        fee_refunded=fee_refund,
        reason=data.reason,
    )
    db.add(refund)
    db.flush()

    payment.amount_refunded = refunded_after
    payment.fee_refunded = fee_refunded_after
    transition(payment, "refunded" if refunded_after == payment.amount_captured else "partially_refunded")
    ledger.record_refund(db, payment, refund)
    outbox.emit(db, merchant.id, "refund.succeeded", serialize_refund(refund))
    db.flush()
    return serialize_refund(refund)


def list_payments(
    db: Session, merchant_id: str, limit: int, starting_after: str | None
) -> tuple[list[dict[str, Any]], bool]:
    """Keyset (cursor) pagination: stable and fast on large tables, unlike OFFSET."""
    stmt = select(Payment).where(Payment.merchant_id == merchant_id)
    if starting_after:
        cursor = get_payment(db, merchant_id, starting_after)
        stmt = stmt.where(
            tuple_(Payment.created_at, Payment.id) < tuple_(cursor.created_at, cursor.id)
        )
    rows = db.scalars(
        stmt.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit + 1)
    ).all()
    return [serialize_payment(p) for p in rows[:limit]], len(rows) > limit
