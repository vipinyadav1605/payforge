from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import AuthContext, get_auth
from ..errors import ApiError
from ..models import WebhookAttempt, WebhookDelivery, WebhookEndpoint
from ..schemas import WebhookEndpointCreate, WebhookEndpointOut
from ..security import generate_webhook_secret
from ..urlcheck import validate_webhook_url

router = APIRouter(prefix="/v1", tags=["webhooks"])


def _endpoint_out(e: WebhookEndpoint, include_secret: bool = False) -> dict:
    return {
        "id": e.id,
        "url": e.url,
        "events": e.events,
        "active": e.active,
        "created": int(e.created_at.timestamp()),
        "secret": e.secret if include_secret else None,
    }


@router.post("/webhook-endpoints", response_model=WebhookEndpointOut, status_code=201)
def create_endpoint(
    body: WebhookEndpointCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
):
    validate_webhook_url(body.url, get_settings().env)
    endpoint = WebhookEndpoint(
        merchant_id=ctx.merchant.id,
        url=body.url,
        events=body.events,
        secret=generate_webhook_secret(),
    )
    db.add(endpoint)
    db.commit()
    return _endpoint_out(endpoint, include_secret=True)  # the secret is shown only now


@router.get("/webhook-endpoints", response_model=list[WebhookEndpointOut])
def list_endpoints(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.merchant_id == ctx.merchant.id, WebhookEndpoint.active.is_(True))
        .order_by(WebhookEndpoint.created_at)
    ).all()
    return [_endpoint_out(e) for e in rows]


@router.delete("/webhook-endpoints/{endpoint_id}", status_code=204)
def delete_endpoint(
    endpoint_id: str, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
):
    endpoint = db.get(WebhookEndpoint, endpoint_id)
    if endpoint is None or endpoint.merchant_id != ctx.merchant.id:
        raise ApiError(404, "endpoint_not_found", "No such webhook endpoint.")
    endpoint.active = False
    db.commit()


@router.get("/webhook-deliveries")
def list_deliveries(
    status: str | None = Query(default=None, pattern="^(pending|retrying|succeeded|dead)$"),
    limit: int = Query(20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    stmt = select(WebhookDelivery).where(WebhookDelivery.merchant_id == ctx.merchant.id)
    if status:
        stmt = stmt.where(WebhookDelivery.status == status)
    rows = db.scalars(stmt.order_by(WebhookDelivery.created_at.desc()).limit(limit)).all()
    out = []
    for d in rows:
        attempts = db.scalars(
            select(WebhookAttempt)
            .where(WebhookAttempt.delivery_id == d.id)
            .order_by(WebhookAttempt.attempt_no)
        ).all()
        out.append(
            {
                "id": d.id,
                "event_id": d.event_id,
                "endpoint_id": d.endpoint_id,
                "status": d.status,
                "attempts": d.attempts,
                "last_status_code": d.last_status_code,
                "last_error": d.last_error,
                "attempt_log": [
                    {
                        "attempt": a.attempt_no,
                        "status": a.response_status,
                        "error": a.error,
                        "duration_ms": a.duration_ms,
                    }
                    for a in attempts
                ],
            }
        )
    return {"object": "list", "data": out}


@router.post("/webhook-deliveries/{delivery_id}/replay")
def replay_delivery(
    delivery_id: str, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
):
    """Dead-letter replay: put a failed/dead delivery back in the queue."""
    d = db.get(WebhookDelivery, delivery_id)
    if d is None or d.merchant_id != ctx.merchant.id:
        raise ApiError(404, "delivery_not_found", "No such webhook delivery.")
    d.status = "pending"
    d.attempts = 0
    d.next_attempt_at = datetime.now(UTC)
    db.commit()
    return {"id": d.id, "status": d.status}
