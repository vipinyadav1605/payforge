from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import AuthContext, get_auth, require_admin
from ..ledger import merchant_balances
from ..models import ApiKey, Merchant
from ..schemas import BalanceOut, MerchantCreate
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


@router.get("/v1/me")
def me(ctx: AuthContext = Depends(get_auth)):
    return {"id": ctx.merchant.id, "name": ctx.merchant.name, "email": ctx.merchant.email}


@router.get("/v1/balance", response_model=BalanceOut)
def balance(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return {"object": "balance", "available": merchant_balances(db, ctx.merchant.id)}
