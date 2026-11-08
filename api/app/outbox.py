import time
from typing import Any

from sqlalchemy.orm import Session

from .ids import new_id
from .models import OutboxEvent


def emit(db: Session, merchant_id: str, event_type: str, obj: dict[str, Any]) -> OutboxEvent:
    """Record a domain event in the same transaction as the change that caused it.
    Nothing is sent here: the worker's relay delivers it, so a crash can never lose an event
    or announce one whose transaction rolled back."""
    event_id = new_id("evt")
    event = OutboxEvent(
        id=event_id,
        merchant_id=merchant_id,
        type=event_type,
        payload={
            "id": event_id,
            "type": event_type,
            "created": int(time.time()),
            "data": {"object": obj},
        },
    )
    db.add(event)
    return event
