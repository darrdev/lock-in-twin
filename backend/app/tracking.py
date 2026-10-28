"""Pure tracking logic: turn a list of events into a current status or today's stats.

Nothing here touches the database or the web. Every function takes plain values
in and returns plain values out, so the tests can feed it fake event lists.

Time rules (from the Notion guide, step 0.8):
- Every datetime in here is timezone-aware UTC. SQLModel already saves times as
  UTC and returns them labelled as UTC, so events arrive this way.
- "Today" means today in Singapore time, which is UTC+8 with no daylight saving.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, Protocol

from app.models import EventType, State, StatsOut, StatusOut

# Singapore never changes its clocks, so a fixed offset is exact.
# (zoneinfo would need the extra "tzdata" package on Windows.)
LOCAL_TZ = timezone(timedelta(hours=8), "SGT")

Interval = tuple[datetime, datetime]


class EventLike(Protocol):
    """Anything with these three attributes works, e.g. an Event row."""

    type: str
    ts: datetime
    is_false_detection: bool


# ---------- Time helpers ----------

def utc_now() -> datetime:
    """The current time in UTC, labelled as UTC."""
    return datetime.now(timezone.utc)


def today_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    """Start and end of today in Singapore time, given and returned in UTC.

    Example: at 01:00 SGT on 28 Oct, today is 28 Oct 00:00 SGT to 29 Oct 00:00 SGT,
    which is 27 Oct 16:00 UTC to 28 Oct 16:00 UTC.
    """
    local_now = now_utc.astimezone(LOCAL_TZ)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = local_midnight.astimezone(timezone.utc)
    return start, start + timedelta(days=1)


# ---------- Building blocks ----------

def real_events_sorted(events: Iterable[EventLike]) -> list[EventLike]:
    """Drop false detections and sort oldest first."""
    return sorted((e for e in events if not e.is_false_detection), key=lambda e: e.ts)


def pair_intervals(
    events: list[EventLike], start_type: EventType, end_type: EventType, now: datetime
) -> list[Interval]:
    """Pair each start with the next end, e.g. phone_start 2:00 + phone_end 2:03.

    - A start with no end yet (still on the phone) lasts until `now`.
    - A second start while one is already open is ignored (duplicate).
    - An end with no open start is ignored (e.g. the start was yesterday).
    Expects `events` already filtered and sorted.
    """
    intervals: list[Interval] = []
    open_start: datetime | None = None
    for e in events:
        if e.type == start_type and open_start is None:
            open_start = e.ts
        elif e.type == end_type and open_start is not None:
            intervals.append((open_start, e.ts))
            open_start = None
    if open_start is not None:
        intervals.append((open_start, max(now, open_start)))
    return intervals


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Join overlapping intervals so overlapping time is only counted once.

    Needed because a break can overlap a pickup: phone 2:00-2:10 and away
    2:05-2:20 is 20 minutes not focused, not 25.
    """
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _minutes(seconds: float) -> float:
    return round(seconds / 60, 1)


def _total_seconds(intervals: list[Interval]) -> float:
    return sum((end - start).total_seconds() for start, end in intervals)


# ---------- Public functions used by the routers ----------

def compute_stats(events: Iterable[EventLike], now: datetime) -> StatsOut:
    """Today's numbers for GET /stats/today.

    Tracked time runs from the first real event of the day until `now`.
    Focus is tracked time that is neither phone time nor away time.
    """
    real = real_events_sorted(events)
    if not real:
        return StatsOut(
            focus_minutes=0, phone_pickups=0, phone_minutes=0,
            breaks=0, break_minutes=0, longest_focus_minutes=0,
        )

    phone = pair_intervals(real, EventType.phone_start, EventType.phone_end, now)
    away = pair_intervals(real, EventType.away_start, EventType.away_end, now)

    window_start = real[0].ts
    window_end = max(now, real[-1].ts)
    not_focused = merge_intervals(phone + away)

    tracked_s = (window_end - window_start).total_seconds()
    focus_s = max(0.0, tracked_s - _total_seconds(not_focused))

    # Longest focus stretch = the biggest gap between not-focused intervals.
    longest_s = 0.0
    cursor = window_start
    for start, end in not_focused:
        longest_s = max(longest_s, (start - cursor).total_seconds())
        cursor = max(cursor, end)
    longest_s = max(longest_s, (window_end - cursor).total_seconds())

    return StatsOut(
        focus_minutes=_minutes(focus_s),
        phone_pickups=len(phone),
        phone_minutes=_minutes(_total_seconds(phone)),
        breaks=len(away),
        break_minutes=_minutes(_total_seconds(away)),
        longest_focus_minutes=_minutes(longest_s),
    )


def current_status(events: Iterable[EventLike], day_start: datetime) -> StatusOut:
    """What am I doing right now, for GET /status/current (Notion step 2A).

    1. A phone_start with no phone_end after it: phone, since that start.
    2. Else an away_start with no away_end after it: away, since that start.
    3. Else focus, since the latest end event, or the start of the day.
    """
    phone_open: datetime | None = None
    away_open: datetime | None = None
    last_end: datetime | None = None

    for e in real_events_sorted(events):
        if e.type == EventType.phone_start and phone_open is None:
            phone_open = e.ts
        elif e.type == EventType.phone_end:
            phone_open = None
            last_end = e.ts
        elif e.type == EventType.away_start and away_open is None:
            away_open = e.ts
        elif e.type == EventType.away_end:
            away_open = None
            last_end = e.ts

    if phone_open is not None:
        return StatusOut(state=State.phone, since=phone_open)
    if away_open is not None:
        return StatusOut(state=State.away, since=away_open)
    return StatusOut(state=State.focus, since=last_end or day_start)
