from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_CURRENCIES = {"usd", "inr", "eur", "gbp"}


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = Field(gt=0, le=100_000_000, description="Smallest currency unit (cents/paise)")
    currency: str
    payment_method: str = Field(
        min_length=1,
        max_length=100,
        description="Mock PSP tokens: pm_card_visa, pm_card_declined, pm_card_insufficient_funds",
    )
    capture: bool = True
    description: str | None = Field(default=None, max_length=500)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        v = v.lower()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"unsupported currency; use one of {sorted(SUPPORTED_CURRENCIES)}")
        return v

    @field_validator("metadata")
    @classmethod
    def _metadata(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20 or any(len(k) > 40 or len(x) > 500 for k, x in v.items()):
            raise ValueError("metadata: max 20 keys, key<=40 chars, value<=500 chars")
        return v


class PaymentOut(BaseModel):
    id: str
    object: Literal["payment"] = "payment"
    amount: int
    currency: str
    status: str
    payment_method: str
    description: str | None
    metadata: dict[str, str]
    amount_captured: int
    amount_refunded: int
    fee_amount: int
    failure_code: str | None
    created: int


class PaymentList(BaseModel):
    object: Literal["list"] = "list"
    data: list[PaymentOut]
    has_more: bool


class RefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int | None = Field(default=None, gt=0, description="Defaults to the full remaining amount")
    reason: str | None = Field(default=None, max_length=200)


class RefundOut(BaseModel):
    id: str
    object: Literal["refund"] = "refund"
    payment_id: str
    amount: int
    fee_refunded: int
    status: str
    reason: str | None
    created: int


class MerchantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)


class MerchantStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "suspended"]


class WebhookEndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=2000)
    events: list[str] = Field(default_factory=lambda: ["*"])


class WebhookEndpointOut(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    created: int
    secret: str | None = None  # only returned once, at creation


class BalanceOut(BaseModel):
    object: Literal["balance"] = "balance"
    available: dict[str, int]


def error_envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"type": "api_error", "code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}
