from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def is_tuesday_7am_eastern(now: datetime | None = None) -> bool:
    eastern = ZoneInfo("America/New_York")
    current = now.astimezone(eastern) if now else datetime.now(eastern)
    return current.weekday() == 1 and current.hour == 7
