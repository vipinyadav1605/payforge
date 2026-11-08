"""A fake payment service provider (bank/acquirer), driven by magic payment-method tokens.

Real PSPs (Razorpay/Stripe) will plug in behind the same `authorize` signature in a later phase.
NOTE: in production you never hold a DB transaction open across a slow network call to a PSP;
see docs/ARCHITECTURE.md ("Known simplifications").
"""

import uuid
from dataclasses import dataclass


@dataclass
class PSPResult:
    approved: bool
    reference: str
    failure_code: str | None = None


_DECLINES = {
    "pm_card_declined": "card_declined",
    "pm_card_insufficient_funds": "insufficient_funds",
    "pm_card_expired": "expired_card",
}


def authorize(payment_method: str, amount: int, currency: str) -> PSPResult:
    ref = "psp_" + uuid.uuid4().hex[:16]
    if payment_method == "pm_card_visa":
        return PSPResult(True, ref)
    if payment_method in _DECLINES:
        return PSPResult(False, ref, _DECLINES[payment_method])
    return PSPResult(False, ref, "invalid_payment_method")
