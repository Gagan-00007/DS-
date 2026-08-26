"""
Admin-only management endpoints: sections, teachers, timetable, student
enrollment (photo upload OR webcam capture), audit log search, CSV report
export, and analytics summary data for the dashboard.
"""

import base64
import csv
import io
import json
from datetime import date as date_type, datetime, timedelta
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import recognition
from auth import hash_password
from database import get_db
from models import (
    User, Role, Section, Student, EnrolledFace, TimetableEntry,
    AttendanceRecord, AttendanceStatus, AuditLog,
)

router = APIRouter(prefix="/admin", tags=["admin"])

admin_only = auth.require_role(Role.admin)


# ---------- Sections ----------

class SectionCreate(BaseModel):
    name: str


@router.get("/sections")
def list_sections(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [{"id": s.id, "name": s.name} for s in db.query(Section).all()]


@router.post("/sections")
def create_section(req: SectionCreate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if db.query(Section).filter(Section.name == req.name).first():
        raise HTTPException(status_code=400, detail="A section with this name already exists")
    section = Section(name=req.name)
    db.add(section)
    db.commit()
    db.refresh(section)
    return {"id": section.id, "name": section.name}


# ---------- Teachers ----------

class TeacherCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str = "teacher123"


@router.get("/teachers")
def list_teachers(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    teachers = db.query(User).filter(User.role == Role.teacher).all()
    return [{"id": t.id, "email": t.email, "full_name": t.full_name} for t in teachers]


@router.post("/teachers")
def create_teacher(req: TeacherCreate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    teacher = User(
        username=req.username, email=req.email, full_name=req.full_name, role=Role.teacher,
        hashed_password=hash_password(req.password),
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return {"id": teacher.id, "email": teacher.email, "full_name": teacher.full_name}


# ---------- Timetable ----------

class TimetableCreate(BaseModel):
    section_id: int
    teacher_id: int
    subject: str
    room: str
    day_of_week: int
    start_time: str
    end_time: str
    late_grace_minutes: int = 10
    early_exit_buffer_minutes: int = 10


def _parse_time(value: str):
    from datetime import time as time_type
    parts = [int(p) for p in value.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time_type(*parts[:3])


@router.get("/timetable")
def list_timetable(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    entries = db.query(TimetableEntry).all()
    return [
        {
            "id": e.id, "section": e.section.name, "teacher": e.teacher.full_name,
            "subject": e.subject, "room": e.room, "day_of_week": e.day_of_week,
            "start_time": e.start_time.isoformat(), "end_time": e.end_time.isoformat(),
        }
        for e in entries
    ]


@router.post("/timetable")
def create_timetable_entry(req: TimetableCreate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    entry = TimetableEntry(
        section_id=req.section_id, teacher_id=req.teacher_id, subject=req.subject,
        room=req.room, day_of_week=req.day_of_week,
        start_time=_parse_time(req.start_time), end_time=_parse_time(req.end_time),
        late_grace_minutes=req.late_grace_minutes,
        early_exit_buffer_minutes=req.early_exit_buffer_minutes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id}


# ---------- Students / enrollment ----------

@router.get("/students")
def list_students(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    students = db.query(Student).all()
    return [
        {
            "id": s.id, "full_name": s.user.full_name, "email": s.user.email,
            "section": s.section.name, "has_face": s.face is not None,
        }
        for s in students
    ]


def _create_student_user(db: Session, username: str, email: str, full_name: str, section_id: int, password: str) -> Student:
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="A user with this username already exists")
    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")

    user = User(username=username, email=email, full_name=full_name, role=Role.student, hashed_password=hash_password(password))
    db.add(user)
    db.flush()
    student = Student(user_id=user.id, section_id=section.id)
    db.add(student)
    db.flush()
    return student


def _save_embedding_or_fail(db: Session, student: Student, frames: List[np.ndarray]):
    embedding = None
    for frame in frames:
        embedding = recognition._extract_embedding(frame)
        if embedding is not None:
            break
    if embedding is None:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="No face detected in any of the provided photos/frames. Try better lighting or a more front-facing shot.",
        )
    face = EnrolledFace(student_id=student.id, embedding=json.dumps(embedding.tolist()))
    db.add(face)
    db.commit()


@router.post("/students/enroll-upload")
def enroll_student_upload(
    username: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(...),
    section_id: int = Form(...),
    password: str = Form("student123"),
    photos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    student = _create_student_user(db, username, email, full_name, section_id, password)

    frames = []
    for photo in photos:
        contents = photo.file.read()
        arr = np.frombuffer(contents, dtype=np.uint8)
        frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame_bgr is not None:
            frames.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    if not frames:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not decode any uploaded photos.")

    _save_embedding_or_fail(db, student, frames)
    return {"id": student.id, "email": email, "full_name": full_name, "enrolled": True}


class EnrollWebcamRequest(BaseModel):
    username: str
    email: str
    full_name: str
    section_id: int
    password: str = "student123"
    frames_base64: List[str]


@router.post("/students/enroll-webcam")
def enroll_student_webcam(
    req: EnrollWebcamRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    student = _create_student_user(db, req.username, req.email, req.full_name, req.section_id, req.password)

    frames = []
    for b64_str in req.frames_base64:
        img_bytes = base64.b64decode(b64_str)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame_bgr is not None:
            frames.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    if not frames:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not decode any captured frames.")

    _save_embedding_or_fail(db, student, frames)
    return {"id": student.id, "email": req.email, "full_name": req.full_name, "enrolled": True}


# ---------- Audit log search ----------

@router.get("/audit-logs")
def search_audit_logs(
    student_name: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    query = (
        db.query(AuditLog)
        .join(AttendanceRecord, AttendanceRecord.id == AuditLog.attendance_record_id)
        .join(Student, Student.id == AttendanceRecord.student_id)
        .join(User, User.id == Student.user_id)
    )
    if student_name:
        query = query.filter(User.full_name.ilike(f"%{student_name}%"))
    if status:
        query = query.filter(AuditLog.new_status == status)
    if date_from:
        query = query.filter(AuditLog.changed_at >= datetime(date_from.year, date_from.month, date_from.day))
    if date_to:
        day_end = datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
        query = query.filter(AuditLog.changed_at < day_end)

    logs = query.order_by(AuditLog.changed_at.desc()).limit(200).all()
    return [
        {
            "id": l.id,
            "student_name": l.attendance_record.student.user.full_name,
            "changed_by": l.changed_by.full_name,
            "previous_status": l.previous_status.value,
            "new_status": l.new_status.value,
            "reason": l.reason,
            "changed_at": l.changed_at.isoformat(),
        }
        for l in logs
    ]


# ---------- Reports / CSV export ----------

@router.get("/reports/attendance/export")
def export_attendance_csv(
    section_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    query = db.query(AttendanceRecord).join(Student, Student.id == AttendanceRecord.student_id)
    if section_id:
        query = query.filter(Student.section_id == section_id)
    if date_from:
        query = query.filter(AttendanceRecord.date >= datetime(date_from.year, date_from.month, date_from.day))
    if date_to:
        day_end = datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
        query = query.filter(AttendanceRecord.date < day_end)

    records = query.order_by(AttendanceRecord.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name", "Email", "Section", "Date", "Status", "Entry Time", "Exit Time", "Confidence", "Corrected"])
    for r in records:
        writer.writerow([
            r.student.user.full_name, r.student.user.email, r.student.section.name,
            r.date.date().isoformat(), r.status.value,
            r.entry_time.isoformat() if r.entry_time else "",
            r.exit_time.isoformat() if r.exit_time else "",
            r.recognition_confidence if r.recognition_confidence is not None else "",
            "Yes" if r.is_corrected else "No",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_report.csv"},
    )


# ---------- Analytics summary ----------

@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    total_students = db.query(Student).count()
    total_teachers = db.query(User).filter(User.role == Role.teacher).count()
    total_sections = db.query(Section).count()

    raw_status_counts = (
        db.query(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .group_by(AttendanceRecord.status)
        .all()
    )
    status_counts = {k.value: v for k, v in raw_status_counts}

    total_records = sum(status_counts.values())
    present_like = (
        status_counts.get("present", 0)
        + status_counts.get("late", 0)
        + status_counts.get("left_early", 0)
    )
    overall_rate = round((present_like / total_records) * 100, 1) if total_records else 0.0

    section_breakdown = []
    for section in db.query(Section).all():
        sec_records = (
            db.query(AttendanceRecord)
            .join(Student, Student.id == AttendanceRecord.student_id)
            .filter(Student.section_id == section.id)
            .all()
        )
        sec_total = len(sec_records)
        sec_present = sum(
            1 for r in sec_records
            if r.status in (AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.left_early)
        )
        section_breakdown.append({
            "section": section.name,
            "total_records": sec_total,
            "attendance_rate": round((sec_present / sec_total) * 100, 1) if sec_total else 0.0,
        })

    today = date_type.today()
    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        day_records = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.date >= day_start, AttendanceRecord.date < day_end)
            .all()
        )
        day_total = len(day_records)
        day_present = sum(
            1 for r in day_records
            if r.status in (AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.left_early)
        )
        trend.append({
            "date": day.isoformat(),
            "attendance_rate": round((day_present / day_total) * 100, 1) if day_total else 0.0,
        })

    return {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_sections": total_sections,
        "status_counts": status_counts,
        "overall_attendance_rate": overall_rate,
        "section_breakdown": section_breakdown,
        "trend_last_7_days": trend,
    }
