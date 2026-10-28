from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.models import StatsOut
from app.routers.events import get_today_events
from app.tracking import compute_stats, utc_now

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/today", response_model=StatsOut)
def read_today_stats(session: Session = Depends(get_session)):
    return compute_stats(get_today_events(session), now=utc_now())
