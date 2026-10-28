"""Webcam detector: watches the desk and reports phone / away changes to the API.

Run from the repo root, with the venv active and the backend running:
    python cv/detector.py
Press q in the video window to quit.

How it works:
1. Every half second, YOLO looks at a webcam frame for a person and a phone.
2. That gives a raw guess: focus, phone or away. Raw guesses flicker, so a new
   state only counts once it has lasted long enough (the thresholds).
3. When the confirmed state changes, the matching events are sent to
   POST /events, timestamped when the change really began.
"""

import os
import time
from datetime import datetime, timezone

import cv2
import httpx
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()  # reads API_URL from .env if it exists
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

MODEL_NAME = "yolo11n.pt"  # the nano model: small and fast on a laptop. Downloads on first run.
PERSON_CLASS = 0           # class numbers in the COCO dataset YOLO was trained on
PHONE_CLASS = 67
MIN_CONFIDENCE = 0.4       # ignore detections YOLO is less sure about than this
DETECT_EVERY_S = 0.5       # run YOLO about twice a second

# Used if GET /settings isn't available yet (KK's step 1C).
DEFAULT_PICKUP_S = 3
DEFAULT_BREAK_S = 60
# How long you must look focused again before a pickup or break ends.
# Stops one missed phone detection from splitting a pickup in two.
RETURN_TO_FOCUS_S = 5

# Which events to send for each confirmed change (old state, new state).
TRANSITION_EVENTS = {
    ("focus", "phone"): ["phone_start"],
    ("phone", "focus"): ["phone_end"],
    ("focus", "away"): ["away_start"],
    ("away", "focus"): ["away_end"],
    ("phone", "away"): ["phone_end", "away_start"],
    ("away", "phone"): ["away_end", "phone_start"],
}


def load_thresholds() -> tuple[float, float]:
    """Pickup and break thresholds from GET /settings, or the defaults."""
    try:
        response = httpx.get(f"{API_URL}/settings", timeout=2)
        response.raise_for_status()
        data = response.json()
        return float(data["pickup_threshold_s"]), float(data["break_threshold_s"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        print(f"Using default thresholds, couldn't read /settings ({error})")
        return DEFAULT_PICKUP_S, DEFAULT_BREAK_S


def detect_state(model: YOLO, frame) -> str:
    """One raw guess from one frame: 'away', 'phone' or 'focus'."""
    result = model(frame, conf=MIN_CONFIDENCE, classes=[PERSON_CLASS, PHONE_CLASS], verbose=False)[0]
    found = {int(c) for c in result.boxes.cls}
    if PERSON_CLASS not in found:
        return "away"
    if PHONE_CLASS in found:
        return "phone"
    return "focus"


class StateTracker:
    """Turns flickering raw guesses into confirmed state changes."""

    def __init__(self, pickup_s: float, break_s: float):
        self.needed_s = {"phone": pickup_s, "away": break_s, "focus": RETURN_TO_FOCUS_S}
        self.state = "focus"
        self.candidate: str | None = None
        self.candidate_since: datetime | None = None

    def update(self, raw: str, now: datetime) -> tuple[str, str, datetime] | None:
        """Feed one raw guess. Returns (old, new, when it began) on a confirmed change."""
        if raw == self.state:
            self.candidate = None  # back to normal, forget the half-started change
            return None
        if raw != self.candidate:
            self.candidate, self.candidate_since = raw, now  # a new possible change starts
            return None
        if (now - self.candidate_since).total_seconds() < self.needed_s[raw]:
            return None  # not long enough yet
        old, began = self.state, self.candidate_since
        self.state, self.candidate = raw, None
        return old, raw, began


def send_event(client: httpx.Client, event_type: str, ts: datetime) -> None:
    """POST one event. If the API is down, print and carry on (never crash)."""
    try:
        response = client.post(f"{API_URL}/events", json={"type": event_type, "ts": ts.isoformat()})
        response.raise_for_status()
        print(f"  sent {event_type} at {ts:%H:%M:%S} UTC")
    except httpx.HTTPError as error:
        print(f"  couldn't send {event_type}: {error}")


def main() -> None:
    pickup_s, break_s = load_thresholds()
    print(f"Pickup after {pickup_s:g}s, break after {break_s:g}s. Press q to quit.")

    model = YOLO(MODEL_NAME)
    tracker = StateTracker(pickup_s, break_s)
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Couldn't open the webcam.")
        return

    last_detect = 0.0
    raw = "focus"
    with httpx.Client(timeout=2) as client:
        try:
            while True:
                ok, frame = camera.read()
                if not ok:
                    print("Couldn't read a frame from the webcam.")
                    break

                if time.monotonic() - last_detect >= DETECT_EVERY_S:
                    last_detect = time.monotonic()
                    raw = detect_state(model, frame)
                    change = tracker.update(raw, datetime.now(timezone.utc))
                    if change:
                        old, new, began = change
                        print(f"{old.upper()} -> {new.upper()}")
                        for event_type in TRANSITION_EVENTS[(old, new)]:
                            send_event(client, event_type, began)

                label = f"{tracker.state.upper()}  (seeing: {raw})"
                cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow("lock-in-twin", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            camera.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
