"""KPIs shown on the back-office home page. Pure read-only queries."""

from datetime import timedelta

from django.db.models import BigIntegerField, Case, F, Q, Sum, When
from django.utils import timezone

from .models import LedgerEntry, Merchant, OutboxEvent, Payment, WebhookDelivery

SUCCESS_STATUSES = ("authorized", "captured", "partially_refunded", "refunded")


def money(minor: int | None, currency: str = "") -> str:
    minor = minor or 0
    sign = "-" if minor < 0 else ""
    minor = abs(minor)
    text = f"{sign}{minor // 100:,}.{minor % 100:02d}"
    return f"{text} {currency.upper()}".strip()


def collect() -> list[dict]:
    since = timezone.now() - timedelta(hours=24)
    recent = Payment.objects.filter(created_at__gte=since)
    total = recent.count()
    succeeded = recent.filter(status__in=SUCCESS_STATUSES).count()
    failed = recent.filter(status="failed").count()
    attempted = succeeded + failed

    volume = (
        recent.filter(amount_captured__gt=0)
        .values("currency")
        .annotate(total=Sum("amount_captured"))
        .order_by("currency")
    )
    volume_text = ", ".join(money(v["total"], v["currency"]) for v in volume) or "0.00"

    signed = Case(
        When(direction="credit", then=F("amount")),
        default=-F("amount"),
        output_field=BigIntegerField(),
    )
    fees = (
        LedgerEntry.objects.filter(account__owner_id="platform", account__code="fees")
        .values("account__currency")
        .annotate(net=Sum(signed))
        .order_by("account__currency")
    )
    fees_text = ", ".join(money(f["net"], f["account__currency"]) for f in fees) or "0.00"

    totals = LedgerEntry.objects.aggregate(
        debits=Sum("amount", filter=Q(direction="debit")),
        credits=Sum("amount", filter=Q(direction="credit")),
    )
    debits, credits = totals["debits"] or 0, totals["credits"] or 0
    balanced = debits == credits

    dead = WebhookDelivery.objects.filter(status="dead").count()
    retrying = WebhookDelivery.objects.filter(status="retrying").count()
    backlog = OutboxEvent.objects.filter(processed_at__isnull=True).count()
    merchants = Merchant.objects.count()
    suspended = Merchant.objects.filter(status="suspended").count()

    return [
        {"label": "Payments (24h)", "value": total, "hint": f"{succeeded} ok / {failed} failed", "level": "info"},
        {
            "label": "Success rate (24h)",
            "value": f"{succeeded * 100 / attempted:.1f}%" if attempted else "n/a",
            "hint": "authorized or better vs failed",
            "level": "info",
        },
        {"label": "Captured volume (24h)", "value": volume_text, "hint": "gross, by currency", "level": "info"},
        {"label": "Platform fee revenue", "value": fees_text, "hint": "all time, from the ledger", "level": "info"},
        {
            "label": "Ledger balanced",
            "value": "YES" if balanced else "NO",
            "hint": f"debits {debits} vs credits {credits}",
            "level": "ok" if balanced else "bad",
        },
        {
            "label": "Dead webhooks",
            "value": dead,
            "hint": "need attention / replay",
            "level": "bad" if dead else "ok",
        },
        {
            "label": "Retrying webhooks",
            "value": retrying,
            "hint": "will retry automatically",
            "level": "warn" if retrying else "ok",
        },
        {
            "label": "Outbox backlog",
            "value": backlog,
            "hint": "events not yet fanned out",
            "level": "warn" if backlog > 100 else "ok",
        },
        {
            "label": "Merchants",
            "value": merchants,
            "hint": f"{suspended} suspended",
            "level": "warn" if suspended else "info",
        },
    ]
