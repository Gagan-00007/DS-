"""
Attendance reads (role-scoped) and the correction workflow. Corrections
never overwrite silently — every change appends an AuditLog row alongside
updating the record, per spec section 3.5.
"""

from datetime import date as date_type, datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from models import (
    AttendanceRecord, AttendanceStatus, AuditLog, Student, TimetableEntry, User, Role,
)


def get_attendance_for_student(db: Session, student_id: int) -> List[AttendanceRecord]:
    """Student view — own record only. Caller (main.py route) is
    responsible for checking that the requesting user IS this student."""
    return (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_id)
        .order_by(AttendanceRecord.date.desc())
        .all()
    )


def get_attendance_for_section(
    db: Session, section_id: int, on_date: Optional[date_type] = None
) -> List[AttendanceRecord]:
    """Teacher view — all students in a section, optionally filtered to one date."""
    query = (
        db.query(AttendanceRecord)
        .join(TimetableEntry, TimetableEntry.id == AttendanceRecord.timetable_entry_id)
        .filter(TimetableEntry.section_id == section_id)
    )
    if on_date:
        if isinstance(on_date, str):
            on_date = date_type.fromisoformat(on_date)
        day_start = datetime(on_date.year, on_date.month, on_date.day)
        day_end = day_start + timedelta(days=1)
        query = query.filter(AttendanceRecord.date >= day_start, AttendanceRecord.date < day_end)
    return query.order_by(AttendanceRecord.date.desc()).all()


def correct_attendance(
    db: Session,
    record_id: int,
    new_status: AttendanceStatus,
    reason: str,
    corrected_by: User,
) -> AttendanceRecord:
    """Teacher correction. Requires a reason, writes to AuditLog with the
    previous value preserved, then updates the record. Raises ValueError
    if the record doesn't exist or the reason is empty — caller (route)
    translates that into the right HTTP error."""
    if not reason or not reason.strip():
        raise ValueError("A reason is required for every correction.")

    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
    if record is None:
        raise ValueError(f"No attendance record with id={record_id}")

    audit_entry = AuditLog(
        attendance_record_id=record.id,
        changed_by_id=corrected_by.id,
        previous_status=record.status,
        new_status=new_status,
        reason=reason.strip(),
    )
    db.add(audit_entry)

    record.status = new_status
    record.is_corrected = True
    db.commit()
    db.refresh(record)
    return record


def get_audit_trail(db: Session, record_id: int) -> List[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.attendance_record_id == record_id)
        .order_by(AuditLog.changed_at.asc())
        .all()
    )


def get_absence_count_for_month(db: Session, student_id: int, year: int, month: int) -> int:
    """Used by the monthly absence job (see notifications.py / jobs/)."""
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.status == AttendanceStatus.absent,
        )
        .filter(
            # SQLite-friendly date filtering — extract year/month from the stored date.
            AttendanceRecord.date >= date_type(year, month, 1),
            AttendanceRecord.date < date_type(year + (month == 12), (month % 12) + 1, 1),
        )
        .count()
    )
