from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.models import StatusOut
from app.routers.events import get_today_events
from app.tracking import current_status, today_bounds_utc, utc_now

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/current", response_model=StatusOut)
def read_current_status(session: Session = Depends(get_session)):
    day_start, _ = today_bounds_utc(utc_now())
    return current_status(get_today_events(session), day_start=day_start)
