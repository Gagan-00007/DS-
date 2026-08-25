"""
The core pipeline: a frame burst comes in from a door camera, this module
resolves the active class, runs recognition + liveness against the right
roster, and writes the outcome (attendance or security event).

This is the "engine" — main.py's /checkpoint/scan route is a thin wrapper
around run_checkpoint_pipeline().
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Literal, Optional

import numpy as np
from sqlalchemy.orm import Session

from models import (
    AttendanceRecord, AttendanceStatus, SecurityEvent, SecurityEventType, Student,
)
import timetable
import recognition
import liveness

CheckpointType = Literal["entry", "exit"]


@dataclass
class CheckpointResult:
    status: str  # "marked_present" | "marked_late" | "marked_left_early" |
                 # "spoof_suspected" | "unrecognized" | "no_face" | "no_active_class"
    student_name: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[str] = None


def _log_security_event(db: Session, event_type: SecurityEventType, camera_id: str,
                         checkpoint_type: str, note: str = ""):
    db.add(SecurityEvent(
        event_type=event_type, camera_id=camera_id,
        checkpoint_type=checkpoint_type, note=note,
    ))
    db.commit()


def run_checkpoint_pipeline(
    db: Session,
    frames: List[np.ndarray],
    room: str,
    camera_id: str,
    checkpoint_type: CheckpointType,
) -> CheckpointResult:
    now = datetime.utcnow()

    # 1. Resolve active class for this room right now.
    active_class = timetable.get_active_class(db, room=room, at=now)
    if active_class is None:
        return CheckpointResult(status="no_active_class", timestamp=now.isoformat())

    # 2. Get an embedding from the burst (also serves as our detection check).
    embedding = recognition.get_best_embedding_from_burst(frames)
    if embedding is None:
        _log_security_event(db, SecurityEventType.no_face, camera_id, checkpoint_type)
        return CheckpointResult(status="no_face", timestamp=now.isoformat())

    # 3. Recognize against the active class's roster only.
    result = recognition.recognize_against_roster(db, embedding, active_class.section_id)
    if not result.matched:
        _log_security_event(db, SecurityEventType.unrecognized, camera_id, checkpoint_type)
        return CheckpointResult(status="unrecognized", timestamp=now.isoformat())

    # 4. Liveness check — catches a photo held up to the camera.
    if not liveness.detect_blink(frames):
        _log_security_event(
            db, SecurityEventType.spoof_suspected, camera_id, checkpoint_type,
            note=f"matched_student_id={result.student_id}",
        )
        return CheckpointResult(status="spoof_suspected", timestamp=now.isoformat())

    # 5. Recognized AND live — resolve entry vs exit outcome.
    student = db.query(Student).filter(Student.id == result.student_id).first()
    student_name = student.user.full_name if student else None

    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1)
    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.student_id == result.student_id,
            AttendanceRecord.timetable_entry_id == active_class.id,
            AttendanceRecord.date >= today_start,
            AttendanceRecord.date < today_end,
        )
        .first()
    )

    if checkpoint_type == "entry":
        late = timetable.is_late(active_class, now)
        status_value = AttendanceStatus.late if late else AttendanceStatus.present

        if record is None:
            record = AttendanceRecord(
                student_id=result.student_id,
                timetable_entry_id=active_class.id,
                date=now,
                status=status_value,
                entry_time=now,
                recognition_confidence=result.confidence,
            )
            db.add(record)
        else:
            record.entry_time = now
            record.status = status_value
            record.recognition_confidence = result.confidence
        db.commit()

        return CheckpointResult(
            status="marked_late" if late else "marked_present",
            student_name=student_name, confidence=result.confidence,
            timestamp=now.isoformat(),
        )

    else:  # checkpoint_type == "exit"
        if record is None:
            # Exit event with no prior entry on record — log it but don't
            # fabricate a full attendance row; the absence job will still
            # correctly mark them absent since no entry_time exists anywhere.
            _log_security_event(
                db, SecurityEventType.unrecognized, camera_id, checkpoint_type,
                note=f"exit_without_entry student_id={result.student_id}",
            )
            return CheckpointResult(status="unrecognized", timestamp=now.isoformat())

        record.exit_time = now
        if timetable.is_early_exit(active_class, now):
            record.status = AttendanceStatus.left_early
        db.commit()

        return CheckpointResult(
            status="marked_left_early" if record.status == AttendanceStatus.left_early else "marked_present",
            student_name=student_name, confidence=result.confidence,
            timestamp=now.isoformat(),
        )
