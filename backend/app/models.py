from datetime import datetime
from enum import Enum

from pydantic import AwareDatetime
from sqlmodel import SQLModel, Field


# Fixed lists of allowed values. A value outside the list gets a 422 error automatically.
# Names are lowercase to match the values, because the database stores the name.
class EventType(str, Enum):
    phone_start = "phone_start"
    phone_end = "phone_end"
    away_start = "away_start"
    away_end = "away_end"


class State(str, Enum):
    focus = "focus"
    phone = "phone"
    away = "away"


#Events
class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: EventType
    ts: datetime  # SQLModel saves it as UTC and returns it labelled as UTC
    is_false_detection: bool = False


# What a client may send to POST /events. AwareDatetime rejects a ts without a timezone.
class EventCreate(SQLModel):
    type: EventType
    ts: AwareDatetime


# What a client may send to PUT /events/{id}. Every field is optional: send only what changes.
class EventUpdate(SQLModel):
    type: EventType | None = None
    ts: AwareDatetime | None = None
    is_false_detection: bool | None = None


#Settings, below are some defaults stored in the db. not hardcoded so that a user can change it from the dashboard for example.
class Settings(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    pickup_threshold_s: int = 3
    break_threshold_s: int = 90
    reminders_on: bool = True
    daily_goal_minutes: int = 240

class AlertRule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    state: str
    min_seconds: int
    message: str
    enabled: bool = True

class AlertHistory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rule_id: int = Field(foreign_key="alertrule.id") #rule_id uses a foreign key, which means it must match the id of a real row in the alertrule table. That's how a history row points at the rule that fired.
    sent_at: datetime
    message: str
    status_since: datetime


# Reply shapes (not tables)

# GET /status/current. The handshake with KK's alert checker: don't change without telling KK.
class StatusOut(SQLModel):
    state: State
    since: datetime


# GET /stats/today.
class StatsOut(SQLModel):
    focus_minutes: float
    phone_pickups: int
    phone_minutes: float
    breaks: int
    break_minutes: float
    longest_focus_minutes: float
