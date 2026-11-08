from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    """Liveness probe: the process is up (Kubernetes restarts the pod if this fails)."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe: dependencies are reachable (Kubernetes stops routing traffic if not)."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable", "db": "down"}, status_code=503)
    return {"status": "ok", "db": "up"}
