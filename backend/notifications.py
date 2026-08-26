"""
Monthly absence threshold check -> in-app notification for the relevant
teacher(s). Kept as plain in-app rows for the demo (fastest to build and
show reliably) — email is a stretch goal per spec section 7.
"""

from datetime import date
from typing import List

from sqlalchemy.orm import Session

from models import Notification, Student, TimetableEntry, Role, User
import attendance_store

ABSENCE_THRESHOLD = 7  # configurable — see note in check_and_notify()


def check_and_notify(db: Session, student: Student, year: int, month: int) -> List[Notification]:
    """Check one student's absence count for the given month; if it
    crosses ABSENCE_THRESHOLD, create a notification for each teacher
    who teaches that student's section (via TimetableEntry), unless one
    already exists for this student+month (avoid duplicate spam)."""
    count = attendance_store.get_absence_count_for_month(db, student.id, year, month)
    if count <= ABSENCE_THRESHOLD:
        return []

    month_key = f"{year:04d}-{month:02d}"

    existing = (
        db.query(Notification)
        .filter(Notification.student_id == student.id, Notification.month == month_key)
        .first()
    )
    if existing:
        return []  # already notified for this student this month

    teacher_ids = {
        row.teacher_id
        for row in db.query(TimetableEntry)
        .filter(TimetableEntry.department_id == student.department_id)
        .all()
    }

    created = []
    for teacher_id in teacher_ids:
        notification = Notification(
            teacher_id=teacher_id,
            student_id=student.id,
            message=(
                f"{student.user.full_name} has {count} absences in "
                f"{month_key} — above the {ABSENCE_THRESHOLD}/month threshold."
            ),
            absence_count=count,
            month=month_key,
        )
        db.add(notification)
        created.append(notification)

    db.commit()
    return created


def run_monthly_check_for_all_students(db: Session, year: int = None, month: int = None):
    """Entry point for the scheduled job (see jobs/monthly_absence_check.py).
    Defaults to the current year/month if not given."""
    today = date.today()
    year = year or today.year
    month = month or today.month

    all_students = db.query(Student).all()
    total_notifications = 0
    for student in all_students:
        total_notifications += len(check_and_notify(db, student, year, month))
    return total_notifications


def get_notifications_for_teacher(db: Session, teacher_id: int, unread_only: bool = False):
    query = db.query(Notification).filter(Notification.teacher_id == teacher_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    return query.order_by(Notification.created_at.desc()).all()


def mark_notification_read(db: Session, notification_id: int):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        notification.is_read = True
        db.commit()
    return notification
