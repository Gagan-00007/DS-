"""
Timetable engine — the thing every checkpoint scan calls first to figure
out "what class is happening right now in this room". Everything else
(which roster to match faces against, what counts as late/absent) flows
from this lookup.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models import TimetableEntry


def get_active_class(db: Session, room: str, at: Optional[datetime] = None) -> Optional[TimetableEntry]:
    """Return the TimetableEntry active for `room` at time `at` (defaults
    to now), or None if no class is scheduled. Matches on day-of-week and
    a start_time <= at.time() <= end_time window.
    """
    at = at or datetime.utcnow()
    day_of_week = at.weekday()  # 0=Monday
    current_time = at.time()

    entries = (
        db.query(TimetableEntry)
        .filter(TimetableEntry.room == room, TimetableEntry.day_of_week == day_of_week)
        .all()
    )

    for entry in entries:
        if entry.start_time <= current_time <= entry.end_time:
            return entry
    return None


def is_late(entry: TimetableEntry, arrival: datetime) -> bool:
    """True if `arrival` is after start_time + the entry's grace period."""
    grace_cutoff = (
        datetime.combine(arrival.date(), entry.start_time)
        + timedelta(minutes=entry.late_grace_minutes)
    )
    return arrival > grace_cutoff


def is_early_exit(entry: TimetableEntry, departure: datetime) -> bool:
    """True if `departure` is earlier than end_time minus the entry's
    early-exit buffer — i.e. they left meaningfully before class ended."""
    buffer_cutoff = (
        datetime.combine(departure.date(), entry.end_time)
        - timedelta(minutes=entry.early_exit_buffer_minutes)
    )
    return departure < buffer_cutoff
