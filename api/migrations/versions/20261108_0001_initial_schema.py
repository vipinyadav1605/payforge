"""initial schema: merchants, payments, double-entry ledger, idempotency, outbox, webhooks

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "merchants",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("merchant_id", sa.String(40), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
    )
    op.create_index("ix_api_keys_merchant_id", "api_keys", ["merchant_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("merchant_id", sa.String(40), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("payment_method", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
        sa.Column("psp_reference", sa.String(100), nullable=True),
        sa.Column("failure_code", sa.String(60), nullable=True),
        sa.Column("amount_captured", sa.BigInteger, nullable=False),
        sa.Column("amount_refunded", sa.BigInteger, nullable=False),
        sa.Column("fee_amount", sa.BigInteger, nullable=False),
        sa.Column("fee_refunded", sa.BigInteger, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint("amount_captured <= amount", name="ck_payments_captured_le_amount"),
        sa.CheckConstraint("amount_refunded <= amount_captured", name="ck_payments_refund_le_captured"),
    )
    op.create_index("ix_payments_merchant_created", "payments", ["merchant_id", "created_at", "id"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("payment_id", sa.String(40), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("merchant_id", sa.String(40), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("fee_refunded", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])

    # ------------------------------------------------------------ ledger ----
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("owner_id", sa.String(40), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("owner_id", "code", "currency", name="uq_ledger_account"),
    )
    op.create_table(
        "ledger_transactions",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("merchant_id", sa.String(40), nullable=True),
        sa.Column("ref_type", sa.String(20), nullable=False),
        sa.Column("ref_id", sa.String(40), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("ref_type", "ref_id", name="uq_ledger_tx_ref"),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("transaction_id", sa.String(40), sa.ForeignKey("ledger_transactions.id"), nullable=False),
        sa.Column("account_id", sa.String(40), sa.ForeignKey("ledger_accounts.id"), nullable=False),
        sa.Column("direction", sa.String(6), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("direction in ('debit','credit')", name="ck_entry_direction"),
        sa.CheckConstraint("amount > 0", name="ck_entry_amount_positive"),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])

    # Safety net #1: a transaction's debits must equal its credits. Checked at COMMIT time
    # (DEFERRABLE INITIALLY DEFERRED) so all entries of a transaction can be inserted first.
    op.execute(
        """
        CREATE FUNCTION ledger_check_balanced() RETURNS trigger AS $$
        DECLARE d bigint; c bigint;
        BEGIN
          SELECT COALESCE(SUM(amount) FILTER (WHERE direction = 'debit'), 0),
                 COALESCE(SUM(amount) FILTER (WHERE direction = 'credit'), 0)
            INTO d, c FROM ledger_entries WHERE transaction_id = NEW.transaction_id;
          IF d <> c THEN
            RAISE EXCEPTION 'ledger transaction % unbalanced: debits % credits %',
                            NEW.transaction_id, d, c;
          END IF;
          RETURN NULL;
        END; $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ledger_entries_balanced
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger_check_balanced();
        """
    )
    # Safety net #2: the ledger is append-only. Corrections are new, reversing transactions.
    op.execute(
        """
        CREATE FUNCTION ledger_entries_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'ledger_entries is append-only (% not allowed)', TG_OP;
        END; $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_entries_no_change
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION ledger_entries_immutable();
        """
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("merchant_id", sa.String(40), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_code", sa.Integer, nullable=True),
        sa.Column("response_body", postgresql.JSONB, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("merchant_id", "key", name="uq_idempotency_merchant_key"),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("merchant_id", sa.String(40), nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("processed_at", TS, nullable=True),
    )
    op.create_index(
        "ix_outbox_unprocessed", "outbox_events", ["created_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("merchant_id", sa.String(40), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.String(100), nullable=False),
        sa.Column("events", postgresql.JSONB, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_webhook_endpoints_merchant_id", "webhook_endpoints", ["merchant_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("merchant_id", sa.String(40), nullable=False),
        sa.Column("endpoint_id", sa.String(40), sa.ForeignKey("webhook_endpoints.id"), nullable=False),
        sa.Column("event_id", sa.String(40), sa.ForeignKey("outbox_events.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("next_attempt_at", TS, nullable=False),
        sa.Column("last_status_code", sa.Integer, nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_webhook_deliveries_merchant_id", "webhook_deliveries", ["merchant_id"])
    op.create_index("ix_deliveries_due", "webhook_deliveries", ["status", "next_attempt_at"])

    op.create_table(
        "webhook_attempts",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("delivery_id", sa.String(40), sa.ForeignKey("webhook_deliveries.id"), nullable=False),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_webhook_attempts_delivery_id", "webhook_attempts", ["delivery_id"])


def downgrade() -> None:
    for table in (
        "webhook_attempts", "webhook_deliveries", "webhook_endpoints", "outbox_events",
        "idempotency_keys",
    ):
        op.drop_table(table)
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_no_change ON ledger_entries")
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_balanced ON ledger_entries")
    op.drop_table("ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS ledger_entries_immutable()")
    op.execute("DROP FUNCTION IF EXISTS ledger_check_balanced()")
    for table in (
        "ledger_transactions", "ledger_accounts", "refunds", "payments", "api_keys", "merchants",
    ):
        op.drop_table(table)
