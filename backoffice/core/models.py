"""Read-only mirrors of PayForge's tables (owned and migrated by the FastAPI service via Alembic).

`managed = False` tells Django: the table already exists, never create/alter/drop it.
Secrets are deliberately NOT mapped: api_keys.key_hash and webhook_endpoints.secret.
"""

from django.db import models


class _Mirror(models.Model):
    class Meta:
        abstract = True
        managed = False


class Merchant(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=320)
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "merchants"

    def __str__(self):
        return f"{self.name} ({self.id})"


class ApiKey(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    merchant = models.ForeignKey(Merchant, models.DO_NOTHING, db_constraint=False, related_name="api_keys")
    prefix = models.CharField(max_length=16)
    created_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)

    class Meta(_Mirror.Meta):
        db_table = "api_keys"

    def __str__(self):
        return f"{self.prefix}..."


class Payment(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    merchant = models.ForeignKey(Merchant, models.DO_NOTHING, db_constraint=False, related_name="payments")
    amount = models.BigIntegerField(help_text="Smallest currency unit (cents/paise)")
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=24)
    payment_method = models.CharField(max_length=100)
    description = models.CharField(max_length=500, null=True)
    metadata = models.JSONField()
    psp_reference = models.CharField(max_length=100, null=True)
    failure_code = models.CharField(max_length=60, null=True)
    amount_captured = models.BigIntegerField()
    amount_refunded = models.BigIntegerField()
    fee_amount = models.BigIntegerField()
    fee_refunded = models.BigIntegerField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "payments"

    def __str__(self):
        return self.id


class Refund(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    payment = models.ForeignKey(Payment, models.DO_NOTHING, db_constraint=False, related_name="refunds")
    merchant = models.ForeignKey(Merchant, models.DO_NOTHING, db_constraint=False, related_name="refunds")
    amount = models.BigIntegerField()
    fee_refunded = models.BigIntegerField()
    status = models.CharField(max_length=20)
    reason = models.CharField(max_length=200, null=True)
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "refunds"

    def __str__(self):
        return self.id


class LedgerAccount(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    owner_id = models.CharField(max_length=40)
    code = models.CharField(max_length=40)
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "ledger_accounts"

    def __str__(self):
        return f"{self.owner_id}:{self.code}:{self.currency}"


class LedgerTransaction(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    merchant_id = models.CharField(max_length=40, null=True)
    ref_type = models.CharField(max_length=20)
    ref_id = models.CharField(max_length=40)
    description = models.CharField(max_length=200, null=True)
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "ledger_transactions"

    def __str__(self):
        return self.id


class LedgerEntry(_Mirror):
    id = models.BigIntegerField(primary_key=True)
    transaction = models.ForeignKey(
        LedgerTransaction, models.DO_NOTHING, db_constraint=False, related_name="entries"
    )
    account = models.ForeignKey(LedgerAccount, models.DO_NOTHING, db_constraint=False, related_name="entries")
    direction = models.CharField(max_length=6)
    amount = models.BigIntegerField()
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "ledger_entries"

    def __str__(self):
        return f"{self.direction} {self.amount}"


class OutboxEvent(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    merchant_id = models.CharField(max_length=40)
    type = models.CharField(max_length=60)
    payload = models.JSONField()
    created_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True)

    class Meta(_Mirror.Meta):
        db_table = "outbox_events"

    def __str__(self):
        return f"{self.type} {self.id}"


class WebhookEndpoint(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    merchant = models.ForeignKey(
        Merchant, models.DO_NOTHING, db_constraint=False, related_name="webhook_endpoints"
    )
    url = models.TextField()
    events = models.JSONField()
    active = models.BooleanField()
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "webhook_endpoints"

    def __str__(self):
        return self.url


class WebhookDelivery(_Mirror):
    id = models.CharField(primary_key=True, max_length=40)
    merchant_id = models.CharField(max_length=40)
    endpoint = models.ForeignKey(WebhookEndpoint, models.DO_NOTHING, db_constraint=False, related_name="deliveries")
    event = models.ForeignKey(OutboxEvent, models.DO_NOTHING, db_constraint=False, related_name="deliveries")
    status = models.CharField(max_length=20)
    attempts = models.IntegerField()
    next_attempt_at = models.DateTimeField()
    last_status_code = models.IntegerField(null=True)
    last_error = models.CharField(max_length=300, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "webhook_deliveries"

    def __str__(self):
        return self.id


class WebhookAttempt(_Mirror):
    id = models.BigIntegerField(primary_key=True)
    delivery = models.ForeignKey(WebhookDelivery, models.DO_NOTHING, db_constraint=False, related_name="attempt_log")
    attempt_no = models.IntegerField()
    response_status = models.IntegerField(null=True)
    error = models.CharField(max_length=300, null=True)
    duration_ms = models.IntegerField()
    created_at = models.DateTimeField()

    class Meta(_Mirror.Meta):
        db_table = "webhook_attempts"

    def __str__(self):
        return f"attempt {self.attempt_no}"
