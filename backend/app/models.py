from sqlmodel import SQLModel, Field
from datetime import datetime


#Events
class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: str
    ts: datetime
    is_false_detection: bool = False

class EventCreate(SQLModel):
    type: str
    ts: datetime

#Settings, below are some defaults stored in the db. not hardcoded so that a user can change it from the dashboard for example.
class Settings(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    pickup_threshold_s: int = 3
    break_threshold_s: int = 90
    reminders_on: bool = True
    daily_goal_minutes: int =240

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

class StatusOut(SQLModel):
    state: str
    since: datetime