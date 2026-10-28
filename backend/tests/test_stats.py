"""Tests for the pure tracking logic in app/tracking.py.

No server and no database: each test builds a fake list of events and checks
the numbers. All times are UTC, the same as the database returns them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, State
from app.tracking import compute_stats, current_status, today_bounds_utc

UTC = timezone.utc
DAY_START = datetime(2026, 10, 28, 0, 0, tzinfo=UTC)  # an arbitrary reference point


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return DAY_START.replace(hour=hour, minute=minute, second=second)


def ev(event_type: str, ts: datetime, false_detection: bool = False) -> Event:
    return Event(type=event_type, ts=ts, is_false_detection=false_detection)


# ---------- compute_stats ----------

def test_no_events_gives_all_zeros():
    stats = compute_stats([], now=at(12))
    assert stats.model_dump() == {
        "focus_minutes": 0, "phone_pickups": 0, "phone_minutes": 0,
        "breaks": 0, "break_minutes": 0, "longest_focus_minutes": 0,
    }


def test_one_pickup_of_three_minutes():
    events = [ev("phone_start", at(14, 0)), ev("phone_end", at(14, 3))]
    stats = compute_stats(events, now=at(14, 3))
    assert stats.phone_pickups == 1
    assert stats.phone_minutes == 3
    assert stats.focus_minutes == 0


def test_phone_still_in_hand_counts_up_to_now():
    events = [ev("phone_start", at(14, 0))]
    stats = compute_stats(events, now=at(14, 5))
    assert stats.phone_pickups == 1
    assert stats.phone_minutes == 5


def test_one_break_and_two_pickups():
    events = [
        ev("phone_start", at(9, 0)), ev("phone_end", at(9, 2)),     # 2 min phone
        ev("away_start", at(9, 30)), ev("away_end", at(9, 40)),     # 10 min break
        ev("phone_start", at(10, 0)), ev("phone_end", at(10, 4)),   # 4 min phone
    ]
    stats = compute_stats(events, now=at(11, 0))
    assert stats.phone_pickups == 2
    assert stats.phone_minutes == 6
    assert stats.breaks == 1
    assert stats.break_minutes == 10
    # Tracked 9:00-11:00 = 120 min, minus 6 phone, minus 10 away.
    assert stats.focus_minutes == 104
    # Gaps: 9:02-9:30 (28), 9:40-10:00 (20), 10:04-11:00 (56).
    assert stats.longest_focus_minutes == 56


def test_false_detections_are_ignored():
    events = [
        ev("phone_start", at(9, 0), false_detection=True),
        ev("phone_end", at(9, 20), false_detection=True),
    ]
    assert compute_stats(events, now=at(10)).phone_pickups == 0


def test_break_overlapping_a_pickup_is_not_double_counted():
    events = [
        ev("phone_start", at(9, 0)), ev("phone_end", at(9, 10)),
        ev("away_start", at(9, 5)), ev("away_end", at(9, 20)),
    ]
    stats = compute_stats(events, now=at(9, 30))
    # Not focused 9:00-9:20 (20 min, not 10 + 15). Tracked 30 min.
    assert stats.focus_minutes == 10


def test_events_out_of_order_are_sorted_first():
    events = [ev("phone_end", at(9, 3)), ev("phone_start", at(9, 0))]
    stats = compute_stats(events, now=at(9, 3))
    assert stats.phone_pickups == 1
    assert stats.phone_minutes == 3


# ---------- current_status ----------

def test_status_with_no_events_is_focus_since_start_of_day():
    status = current_status([], day_start=DAY_START)
    assert status.state == State.focus


def test_status_phone_since_open_pickup():
    events = [ev("phone_start", at(14, 0))]
    status = current_status(events, day_start=DAY_START)
    assert status.state == State.phone
    assert status.since == at(14, 0)


def test_status_away_since_open_break():
    events = [ev("away_start", at(15, 0))]
    assert current_status(events, day_start=DAY_START).state == State.away


def test_status_focus_since_last_end():
    events = [ev("phone_start", at(14, 0)), ev("phone_end", at(14, 3))]
    status = current_status(events, day_start=DAY_START)
    assert status.state == State.focus
    assert status.since == at(14, 3)


def test_status_since_is_labelled_utc():
    status = current_status([ev("phone_start", at(14, 0))], day_start=DAY_START)
    assert status.since.utcoffset() == timedelta(0)


# ---------- today_bounds_utc ----------

@pytest.mark.parametrize(
    "now_utc, expected_start",
    [
        # 01:00 SGT on 28 Oct is 17:00 UTC on 27 Oct. Today began 16:00 UTC on 27 Oct.
        (datetime(2026, 10, 27, 17, 0, tzinfo=UTC), datetime(2026, 10, 27, 16, 0, tzinfo=UTC)),
        # 23:00 SGT on 28 Oct is 15:00 UTC on 28 Oct. Same day, same start.
        (datetime(2026, 10, 28, 15, 0, tzinfo=UTC), datetime(2026, 10, 27, 16, 0, tzinfo=UTC)),
    ],
)
def test_today_is_a_singapore_day(now_utc, expected_start):
    start, end = today_bounds_utc(now_utc)
    assert start == expected_start
    assert end == expected_start + timedelta(days=1)
