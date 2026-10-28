from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import Event, EventCreate, EventUpdate
from app.tracking import today_bounds_utc, utc_now

router = APIRouter(prefix="/events", tags=["events"])


def get_today_events(session: Session) -> list[Event]:
    """Today's events (Singapore day), oldest first. Shared with stats and status."""
    start, end = today_bounds_utc(utc_now())
    statement = (
        select(Event)
        .where(Event.ts >= start, Event.ts < end)
        .order_by(Event.ts)
    )
    return list(session.exec(statement).all())


def get_event_or_404(session: Session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("", status_code=201, response_model=Event)
def create_event(event_in: EventCreate, session: Session = Depends(get_session)):
    event = Event.model_validate(event_in)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("/today", response_model=list[Event])
def read_today_events(session: Session = Depends(get_session)):
    return get_today_events(session)


@router.put("/{event_id}", response_model=Event)
def update_event(
    event_id: int, changes: EventUpdate, session: Session = Depends(get_session)
):
    event = get_event_or_404(session, event_id)
    data = changes.model_dump(exclude_unset=True, exclude_none=True)
    event.sqlmodel_update(data)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, session: Session = Depends(get_session)):
    event = get_event_or_404(session, event_id)
    session.delete(event)
    session.commit()
