from django.contrib import admin, messages

from . import api_client
from .models import (
    ApiKey,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Merchant,
    OutboxEvent,
    Payment,
    Refund,
    WebhookAttempt,
    WebhookDelivery,
    WebhookEndpoint,
)
from .stats import money


class ReadOnlyAdmin(admin.ModelAdmin):
    """Nobody edits money tables by hand. Changes go through the API (see api_client)."""

    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ------------------------------------------------------------------ inlines ----
class RefundInline(ReadOnlyInline):
    model = Refund
    fields = ("id", "amount", "fee_refunded", "status", "reason", "created_at")


class LedgerEntryInline(ReadOnlyInline):
    model = LedgerEntry
    fields = ("account", "direction", "amount")
    show_change_link = False


class WebhookAttemptInline(ReadOnlyInline):
    model = WebhookAttempt
    fields = ("attempt_no", "response_status", "error", "duration_ms", "created_at")
    show_change_link = False


class ApiKeyInline(ReadOnlyInline):
    model = ApiKey
    fields = ("id", "prefix", "created_at", "revoked_at")
    show_change_link = False


class WebhookEndpointInline(ReadOnlyInline):
    model = WebhookEndpoint
    fields = ("id", "url", "events", "active", "created_at")


# ------------------------------------------------------------------- admins ----
@admin.register(Merchant)
class MerchantAdmin(ReadOnlyAdmin):
    list_display = ("name", "email", "status", "created_at", "id")
    list_filter = ("status",)
    search_fields = ("id", "name", "email")
    ordering = ("-created_at",)
    inlines = [ApiKeyInline, WebhookEndpointInline]
    actions = ["suspend", "activate"]

    def _set_status(self, request, queryset, status):
        done = 0
        for merchant in queryset[:50]:
            try:
                api_client.set_merchant_status(merchant.id, status)
                done += 1
            except api_client.ApiError as exc:
                self.message_user(request, f"{merchant.id}: {exc}", messages.ERROR)
        if done:
            self.message_user(request, f"{done} merchant(s) set to '{status}' via the PayForge API.")

    @admin.action(description="Suspend selected merchants (their API keys stop working)", permissions=["act"])
    def suspend(self, request, queryset):
        self._set_status(request, queryset, "suspended")

    @admin.action(description="Re-activate selected merchants", permissions=["act"])
    def activate(self, request, queryset):
        self._set_status(request, queryset, "active")

    def has_act_permission(self, request):
        return request.user.is_superuser


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("id", "merchant", "amount_display", "status", "payment_method", "failure_code", "created_at")
    list_filter = ("status", "currency", "payment_method", "created_at")
    search_fields = ("id", "merchant__name", "merchant__email", "psp_reference", "description")
    date_hierarchy = "created_at"
    list_select_related = ("merchant",)
    ordering = ("-created_at",)
    inlines = [RefundInline]

    @admin.display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        return money(obj.amount, obj.currency)


@admin.register(Refund)
class RefundAdmin(ReadOnlyAdmin):
    list_display = ("id", "payment", "amount", "fee_refunded", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "payment__id", "reason")
    ordering = ("-created_at",)


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ReadOnlyAdmin):
    list_display = ("id", "ref_type", "ref_id", "merchant_id", "description", "created_at")
    list_filter = ("ref_type", "created_at")
    search_fields = ("id", "ref_id", "merchant_id", "description")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [LedgerEntryInline]


@admin.register(LedgerAccount)
class LedgerAccountAdmin(ReadOnlyAdmin):
    list_display = ("id", "owner_id", "code", "currency")
    list_filter = ("code", "currency")
    search_fields = ("id", "owner_id")


@admin.register(OutboxEvent)
class OutboxEventAdmin(ReadOnlyAdmin):
    list_display = ("id", "type", "merchant_id", "created_at", "processed_at")
    list_filter = ("type", "created_at")
    search_fields = ("id", "merchant_id")
    ordering = ("-created_at",)


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(ReadOnlyAdmin):
    list_display = ("id", "merchant", "url", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("id", "url", "merchant__name")
    list_select_related = ("merchant",)


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(ReadOnlyAdmin):
    list_display = ("id", "merchant_id", "event", "status", "attempts", "last_error", "next_attempt_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "merchant_id", "event__id", "last_error")
    ordering = ("-created_at",)
    list_select_related = ("event",)
    inlines = [WebhookAttemptInline]
    actions = ["replay"]

    @admin.action(description="Replay selected deliveries (via PayForge API)", permissions=["act"])
    def replay(self, request, queryset):
        done = 0
        for delivery in queryset[:100]:
            try:
                api_client.replay_delivery(delivery.id)
                done += 1
            except api_client.ApiError as exc:
                self.message_user(request, f"{delivery.id}: {exc}", messages.ERROR)
        if done:
            self.message_user(request, f"{done} delivery(ies) queued for retry.")

    def has_act_permission(self, request):
        return request.user.is_superuser
