from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import AuthContext, get_auth, require_admin
from ..errors import ApiError
from ..ledger import merchant_balances
from ..models import ApiKey, Merchant, WebhookDelivery
from ..schemas import BalanceOut, MerchantCreate, MerchantStatusUpdate
from ..security import generate_api_key

router = APIRouter(tags=["merchants"])


@router.post("/admin/merchants", status_code=201, dependencies=[Depends(require_admin)])
def create_merchant(body: MerchantCreate, db: Session = Depends(get_db)):
    """Onboard a merchant. The raw API key is returned ONCE and only its hash is stored."""
    merchant = Merchant(name=body.name, email=body.email)
    db.add(merchant)
    db.flush()
    raw, hashed = generate_api_key()
    db.add(ApiKey(merchant_id=merchant.id, prefix=raw[:12], key_hash=hashed))
    db.commit()
    return {"id": merchant.id, "name": merchant.name, "email": merchant.email, "api_key": raw}


# ----------------------------------------------------------------------------------------
# Back-office operations. The Django back-office READS the database directly but never
# writes to it: every change goes through these endpoints so the API stays the only writer
# (one place for validation, auditing and business rules).
# ----------------------------------------------------------------------------------------
@router.patch("/admin/merchants/{merchant_id}", dependencies=[Depends(require_admin)])
def set_merchant_status(merchant_id: str, body: MerchantStatusUpdate, db: Session = Depends(get_db)):
    """Suspend or re-activate a merchant. A suspended merchant's API keys stop working (403)."""
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise ApiError(404, "merchant_not_found", f"No such merchant: {merchant_id}")
    merchant.status = body.status
    db.commit()
    return {"id": merchant.id, "status": merchant.status}


@router.post("/admin/webhook-deliveries/{delivery_id}/replay", dependencies=[Depends(require_admin)])
def admin_replay_delivery(delivery_id: str, db: Session = Depends(get_db)):
    """Support tool: put any merchant's failed/dead webhook delivery back in the queue."""
    delivery = db.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise ApiError(404, "delivery_not_found", f"No such webhook delivery: {delivery_id}")
    delivery.status = "pending"
    delivery.attempts = 0
    delivery.next_attempt_at = datetime.now(UTC)
    db.commit()
    return {"id": delivery.id, "status": delivery.status}


@router.get("/v1/me")
def me(ctx: AuthContext = Depends(get_auth)):
    return {"id": ctx.merchant.id, "name": ctx.merchant.name, "email": ctx.merchant.email}


@router.get("/v1/balance", response_model=BalanceOut)
def balance(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return {"object": "balance", "available": merchant_balances(db, ctx.merchant.id)}
