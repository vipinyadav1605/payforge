"""Double-entry ledger.

Every money movement is a transaction made of debit and credit entries that MUST balance
(sum of debits == sum of credits). This is enforced twice: here in Python and by a deferred
constraint trigger in the database (see the first migration), so a bug can't corrupt money.

Accounts (per currency):
  platform:clearing   customer money held by PayForge  (balance = debits - credits)
  platform:fees       PayForge revenue                 (balance = credits - debits)
  merchant:balance    owed to the merchant             (balance = credits - debits)

capture of 1000 with fee 25:   DR clearing 1000 | CR merchant:balance 975 | CR fees 25
"""

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .errors import ApiError
from .ids import new_id
from .models import LedgerAccount, LedgerEntry, LedgerTransaction, Payment, Refund

PLATFORM = "platform"
CLEARING = "clearing"
FEES = "fees"
MERCHANT_BALANCE = "balance"


def get_or_create_account(db: Session, owner_id: str, code: str, currency: str) -> LedgerAccount:
    # Race-safe "get or create": concurrent callers can't create duplicates (unique constraint).
    stmt = (
        pg_insert(LedgerAccount)
        .values(id=new_id("acc"), owner_id=owner_id, code=code, currency=currency)
        .on_conflict_do_nothing(constraint="uq_ledger_account")
    )
    db.execute(stmt)
    return db.scalars(
        select(LedgerAccount).where(
            LedgerAccount.owner_id == owner_id,
            LedgerAccount.code == code,
            LedgerAccount.currency == currency,
        )
    ).one()


def post_transaction(
    db: Session,
    *,
    ref_type: str,
    ref_id: str,
    merchant_id: str | None,
    description: str,
    entries: list[tuple[LedgerAccount, str, int]],
) -> LedgerTransaction:
    entries = [e for e in entries if e[2] != 0]
    if any(amount < 0 for _, _, amount in entries):
        raise ValueError("ledger amounts must be positive")
    debits = sum(a for _, d, a in entries if d == "debit")
    credits = sum(a for _, d, a in entries if d == "credit")
    if debits != credits:
        raise ValueError(f"unbalanced ledger transaction: debits={debits} credits={credits}")

    tx = LedgerTransaction(
        merchant_id=merchant_id, ref_type=ref_type, ref_id=ref_id, description=description
    )
    db.add(tx)
    db.flush()
    for account, direction, amount in entries:
        db.add(
            LedgerEntry(
                transaction_id=tx.id, account_id=account.id, direction=direction, amount=amount
            )
        )
    db.flush()
    return tx


def record_capture(db: Session, payment: Payment) -> None:
    clearing = get_or_create_account(db, PLATFORM, CLEARING, payment.currency)
    fees = get_or_create_account(db, PLATFORM, FEES, payment.currency)
    merchant = get_or_create_account(db, payment.merchant_id, MERCHANT_BALANCE, payment.currency)
    net = payment.amount_captured - payment.fee_amount
    post_transaction(
        db,
        ref_type="capture",
        ref_id=payment.id,
        merchant_id=payment.merchant_id,
        description=f"Capture {payment.id}",
        entries=[
            (clearing, "debit", payment.amount_captured),
            (merchant, "credit", net),
            (fees, "credit", payment.fee_amount),
        ],
    )


def record_refund(db: Session, payment: Payment, refund: Refund) -> None:
    clearing = get_or_create_account(db, PLATFORM, CLEARING, payment.currency)
    fees = get_or_create_account(db, PLATFORM, FEES, payment.currency)
    merchant = get_or_create_account(db, payment.merchant_id, MERCHANT_BALANCE, payment.currency)
    post_transaction(
        db,
        ref_type="refund",
        ref_id=refund.id,
        merchant_id=payment.merchant_id,
        description=f"Refund {refund.id} of {payment.id}",
        entries=[
            (merchant, "debit", refund.amount - refund.fee_refunded),
            (fees, "debit", refund.fee_refunded),
            (clearing, "credit", refund.amount),
        ],
    )


def merchant_balances(db: Session, merchant_id: str) -> dict[str, int]:
    signed = case((LedgerEntry.direction == "credit", LedgerEntry.amount), else_=-LedgerEntry.amount)
    rows = db.execute(
        select(LedgerAccount.currency, func.coalesce(func.sum(signed), 0))
        .join(LedgerEntry, LedgerEntry.account_id == LedgerAccount.id)
        .where(LedgerAccount.owner_id == merchant_id, LedgerAccount.code == MERCHANT_BALANCE)
        .group_by(LedgerAccount.currency)
    ).all()
    return {currency: int(total) for currency, total in rows}


def assert_all_balanced(db: Session) -> None:
    """Self-check used by tests/reconciliation: every transaction must balance."""
    rows = db.execute(
        select(
            LedgerEntry.transaction_id,
            func.sum(case((LedgerEntry.direction == "debit", LedgerEntry.amount), else_=0)),
            func.sum(case((LedgerEntry.direction == "credit", LedgerEntry.amount), else_=0)),
        ).group_by(LedgerEntry.transaction_id)
    ).all()
    bad = [r[0] for r in rows if r[1] != r[2]]
    if bad:
        raise ApiError(500, "ledger_unbalanced", f"unbalanced transactions: {bad}")
