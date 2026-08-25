"""
All database tables live here in one file for a hackathon-sized project —
split into backend/models/*.py later if it grows past this.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, Text, Time
)
from sqlalchemy.orm import relationship

from database import Base


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class User(Base):
    """Login account. Students, teachers, and admins are all rows here,
    distinguished by `role`. A student User is linked 1:1 to a Student
    profile (roster membership, enrolled face)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    student_profile = relationship("Student", back_populates="user", uselist=False)


class Section(Base):
    """A class/section, e.g. '10-B'. Students belong to one section;
    teachers can teach multiple sections via TimetableEntry."""
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)  # e.g. "10-B"

    students = relationship("Student", back_populates="section")


class Student(Base):
    """Profile info specific to a student — links a User to a Section
    and to their enrolled face embedding."""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)

    user = relationship("User", back_populates="student_profile")
    section = relationship("Section", back_populates="students")
    face = relationship("EnrolledFace", back_populates="student", uselist=False)


class EnrolledFace(Base):
    """One face embedding per student, produced offline by enroll.py.
    Stored as a serialized float array (128-d for face_recognition,
    varies for other libs) — see enroll.py for how this gets written."""
    __tablename__ = "enrolled_faces"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), unique=True, nullable=False)
    embedding = Column(Text, nullable=False)  # JSON-encoded list of floats
    enrolled_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="face")


class TimetableEntry(Base):
    """One scheduled class slot: which section, which subject, which
    teacher, which room/camera, and when (day of week + start/end time)."""
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String, nullable=False)
    room = Column(String, nullable=False)  # matches camera_id's associated room
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    late_grace_minutes = Column(Integer, default=10)
    early_exit_buffer_minutes = Column(Integer, default=10)

    section = relationship("Section")
    teacher = relationship("User")


class AttendanceStatus(str, enum.Enum):
    present = "present"
    late = "late"
    left_early = "left_early"
    absent = "absent"


class AttendanceRecord(Base):
    """One row per student per timetable period per day. Created/updated
    by the checkpoint pipeline, and can be corrected by a teacher
    (see AuditLog for correction history)."""
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    timetable_entry_id = Column(Integer, ForeignKey("timetable_entries.id"), nullable=False)
    date = Column(DateTime, nullable=False)  # date of the class (time truncated)

    status = Column(Enum(AttendanceStatus), nullable=False)
    entry_time = Column(DateTime, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    recognition_confidence = Column(Float, nullable=True)

    is_corrected = Column(Boolean, default=False)

    student = relationship("Student")
    timetable_entry = relationship("TimetableEntry")


class SecurityEventType(str, enum.Enum):
    spoof_suspected = "spoof_suspected"
    unrecognized = "unrecognized"
    no_face = "no_face"


class SecurityEvent(Base):
    """Every non-success checkpoint outcome — spoof attempts, unrecognized
    faces, no-face frames. Kept separate from AttendanceRecord so the
    dashboard can show a dedicated 'Security Events' view (see spec 3.7)."""
    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(Enum(SecurityEventType), nullable=False)
    camera_id = Column(String, nullable=False)
    checkpoint_type = Column(String, nullable=True)  # "entry" | "exit"
    timestamp = Column(DateTime, default=datetime.utcnow)
    note = Column(String, nullable=True)


class AuditLog(Base):
    """Append-only history of teacher corrections to an AttendanceRecord.
    Never overwrite — always insert a new row here alongside updating
    the record, so a correction can always be traced back."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    attendance_record_id = Column(Integer, ForeignKey("attendance_records.id"), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    previous_status = Column(Enum(AttendanceStatus), nullable=False)
    new_status = Column(Enum(AttendanceStatus), nullable=False)
    reason = Column(Text, nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)

    attendance_record = relationship("AttendanceRecord")
    changed_by = relationship("User")


class Notification(Base):
    """Absence-threshold alert for a teacher. Marked read, never deleted,
    so there's a record the teacher was notified (see spec 3.6)."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    message = Column(String, nullable=False)
    absence_count = Column(Integer, nullable=False)
    month = Column(String, nullable=False)  # "2026-08"
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    teacher = relationship("User")
    student = relationship("Student")
