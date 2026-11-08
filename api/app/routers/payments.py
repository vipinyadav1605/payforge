from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import AuthContext, get_auth
from ..idempotency import fingerprint, run_idempotent
from ..schemas import PaymentCreate, PaymentList, PaymentOut, RefundCreate, RefundOut
from ..services import payments as svc

router = APIRouter(prefix="/v1", tags=["payments"])

IdemKey = Header(default=None, alias="Idempotency-Key", description="Makes retries safe")


def _finish(response: Response, status: int, replayed: bool) -> None:
    response.status_code = status
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    body: PaymentCreate,
    response: Response,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdemKey,
):
    fp = fingerprint("POST", "/v1/payments", body.model_dump(mode="json"))
    status, data, replayed = run_idempotent(
        db, ctx.merchant.id, idempotency_key, fp,
        lambda: (201, svc.create_payment(db, ctx.merchant, body)),
    )
    _finish(response, status, replayed)
    return data


@router.get("/payments", response_model=PaymentList)
def list_payments(
    limit: int = Query(20, ge=1, le=100),
    starting_after: str | None = None,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    data, has_more = svc.list_payments(db, ctx.merchant.id, limit, starting_after)
    return {"object": "list", "data": data, "has_more": has_more}


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: str, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
):
    return svc.serialize_payment(svc.get_payment(db, ctx.merchant.id, payment_id))


@router.post("/payments/{payment_id}/capture", response_model=PaymentOut)
def capture_payment(
    payment_id: str,
    response: Response,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdemKey,
):
    fp = fingerprint("POST", f"/v1/payments/{payment_id}/capture", None)
    status, data, replayed = run_idempotent(
        db, ctx.merchant.id, idempotency_key, fp,
        lambda: (200, svc.capture_payment(db, ctx.merchant, payment_id)),
    )
    _finish(response, status, replayed)
    return data


@router.post("/payments/{payment_id}/cancel", response_model=PaymentOut)
def cancel_payment(
    payment_id: str,
    response: Response,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdemKey,
):
    fp = fingerprint("POST", f"/v1/payments/{payment_id}/cancel", None)
    status, data, replayed = run_idempotent(
        db, ctx.merchant.id, idempotency_key, fp,
        lambda: (200, svc.cancel_payment(db, ctx.merchant, payment_id)),
    )
    _finish(response, status, replayed)
    return data


@router.post("/payments/{payment_id}/refunds", response_model=RefundOut, status_code=201)
def refund_payment(
    payment_id: str,
    body: RefundCreate,
    response: Response,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
    idempotency_key: str | None = IdemKey,
):
    fp = fingerprint("POST", f"/v1/payments/{payment_id}/refunds", body.model_dump(mode="json"))
    status, data, replayed = run_idempotent(
        db, ctx.merchant.id, idempotency_key, fp,
        lambda: (201, svc.refund_payment(db, ctx.merchant, payment_id, body)),
    )
    _finish(response, status, replayed)
    return data
