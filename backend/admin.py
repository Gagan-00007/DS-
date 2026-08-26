"""
Admin-only management endpoints: departments, teachers, timetable, student
enrollment (photo upload OR webcam capture), audit log search, multi-format
report export (CSV/PDF/XLSX), analytics summary, dashboard KPIs, activity
stream, attendance records, backup/restore, and password change.
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
from auth import hash_password, verify_password
from database import get_db
from models import (
    User, Role, Department, Student, EnrolledFace, EnrolledFaceSample,
    TimetableEntry, AttendanceRecord, AttendanceStatus, AuditLog,
    AuditEvent, AuditEventCategory, Notification, SecurityEvent,
)

router = APIRouter(prefix="/admin", tags=["admin"])

admin_only = auth.require_role(Role.admin)


def _log_event(db: Session, action: str, details: str = None,
               user_id: int = None, category: AuditEventCategory = AuditEventCategory.user_action):
    db.add(AuditEvent(user_id=user_id, category=category, action=action, details=details))
    db.commit()


# ---------- Departments ----------

class DepartmentCreate(BaseModel):
    name: str


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [{"id": d.id, "name": d.name} for d in db.query(Department).all()]


@router.post("/departments")
def create_department(req: DepartmentCreate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if db.query(Department).filter(Department.name == req.name).first():
        raise HTTPException(status_code=400, detail="A department with this name already exists")
    dept = Department(name=req.name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    _log_event(db, "create_department", f"Created department: {req.name}", user.id)
    return {"id": dept.id, "name": dept.name}


# ---------- Teachers ----------

class TeacherCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str = "teacher123"


@router.get("/teachers")
def list_teachers(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    teachers = db.query(User).filter(User.role == Role.teacher).all()
    return [
        {"id": t.id, "username": t.username, "email": t.email,
         "full_name": t.full_name, "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in teachers
    ]


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
    _log_event(db, "create_teacher", f"Created teacher: {req.full_name}", user.id)
    return {"id": teacher.id, "email": teacher.email, "full_name": teacher.full_name}


class PasswordResetRequest(BaseModel):
    new_password: str


@router.post("/teachers/{teacher_id}/reset-password")
def reset_teacher_password(teacher_id: int, req: PasswordResetRequest,
                           db: Session = Depends(get_db), user: User = Depends(admin_only)):
    teacher = db.query(User).filter(User.id == teacher_id, User.role == Role.teacher).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    teacher.hashed_password = hash_password(req.new_password)
    db.commit()
    _log_event(db, "reset_password", f"Reset password for teacher: {teacher.full_name}", user.id)
    return {"detail": "Password reset successfully"}


@router.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    teacher = db.query(User).filter(User.id == teacher_id, User.role == Role.teacher).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    db.delete(teacher)
    db.commit()
    _log_event(db, "delete_teacher", f"Deleted teacher: {teacher.full_name}", user.id)
    return {"detail": "Teacher deleted"}


# ---------- Timetable ----------

class TimetableCreate(BaseModel):
    department_id: int
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
            "id": e.id, "department": e.department.name, "teacher": e.teacher.full_name,
            "subject": e.subject, "room": e.room, "day_of_week": e.day_of_week,
            "start_time": e.start_time.isoformat(), "end_time": e.end_time.isoformat(),
        }
        for e in entries
    ]


@router.post("/timetable")
def create_timetable_entry(req: TimetableCreate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    entry = TimetableEntry(
        department_id=req.department_id, teacher_id=req.teacher_id, subject=req.subject,
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
def list_students(
    search: Optional[str] = None, department_id: Optional[int] = None,
    db: Session = Depends(get_db), user: User = Depends(admin_only),
):
    query = db.query(Student)
    if department_id:
        query = query.filter(Student.department_id == department_id)
    students = query.all()
    results = []
    for s in students:
        if search and search.lower() not in s.user.full_name.lower() and search.lower() not in (s.user.username or "").lower():
            continue
        results.append({
            "id": s.id, "user_id": s.user_id, "username": s.user.username,
            "full_name": s.user.full_name, "email": s.user.email,
            "department": s.department.name, "department_id": s.department_id,
            "academic_year": s.academic_year, "section": s.section,
            "roll_number": s.roll_number, "phone_number": s.phone_number,
            "has_face": s.face is not None,
            "encodings_count": 1 if s.face else 0,
            "samples_count": len(s.face_samples),
        })
    return results


@router.get("/students/{student_id}/samples")
def get_student_samples(student_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    samples = db.query(EnrolledFaceSample).filter(EnrolledFaceSample.student_id == student_id).all()
    return [
        {"id": s.id, "image_base64": s.image_base64, "captured_at": s.captured_at.isoformat() if s.captured_at else None}
        for s in samples
    ]


class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    department_id: Optional[int] = None
    academic_year: Optional[str] = None
    section: Optional[str] = None
    roll_number: Optional[str] = None


@router.patch("/students/{student_id}")
def update_student(student_id: int, req: StudentUpdate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if req.full_name is not None:
        student.user.full_name = req.full_name
    if req.email is not None:
        student.user.email = req.email
    if req.phone_number is not None:
        student.phone_number = req.phone_number
    if req.department_id is not None:
        student.department_id = req.department_id
    if req.academic_year is not None:
        student.academic_year = req.academic_year
    if req.section is not None:
        student.section = req.section
    if req.roll_number is not None:
        student.roll_number = req.roll_number
    db.commit()
    return {"detail": "Student updated"}


@router.delete("/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    name = student.user.full_name
    # Delete face and samples (cascade handles samples)
    if student.face:
        db.delete(student.face)
    user_obj = student.user
    db.delete(student)
    db.delete(user_obj)
    db.commit()
    _log_event(db, "delete_student", f"Deleted student: {name}", user.id)
    return {"detail": "Student deleted"}


def _create_student_user(db: Session, username: str, email: str, full_name: str,
                         department_id: int, password: str,
                         academic_year: str = None, section: str = None,
                         roll_number: str = None, phone_number: str = None) -> Student:
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="A user with this username already exists")
    dept = db.query(Department).filter(Department.id == department_id).first()
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    user = User(username=username, email=email, full_name=full_name, role=Role.student,
                hashed_password=hash_password(password))
    db.add(user)
    db.flush()
    student = Student(user_id=user.id, department_id=dept.id,
                      academic_year=academic_year, section=section,
                      roll_number=roll_number, phone_number=phone_number)
    db.add(student)
    db.flush()
    return student


def _save_embedding_and_samples(db: Session, student: Student, frames: List[np.ndarray],
                                 frames_base64: List[str] = None):
    """Extract embedding from best frame AND store all frames as samples."""
    embedding = None
    best_idx = 0
    for i, frame in enumerate(frames):
        emb = recognition._extract_embedding(frame)
        if emb is not None and embedding is None:
            embedding = emb
            best_idx = i

    if embedding is None:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="No face detected in any of the provided photos/frames. Try better lighting or a more front-facing shot.",
        )

    face = EnrolledFace(student_id=student.id, embedding=json.dumps(embedding.tolist()))
    db.add(face)

    # Store all frames as samples
    if frames_base64:
        for b64 in frames_base64:
            sample = EnrolledFaceSample(student_id=student.id, image_base64=b64)
            db.add(sample)
    else:
        # Convert numpy frames to base64 for storage
        for frame in frames:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            _, buf = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buf).decode('utf-8')
            sample = EnrolledFaceSample(student_id=student.id, image_base64=b64)
            db.add(sample)

    db.commit()


@router.post("/students/enroll-upload")
def enroll_student_upload(
    username: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(...),
    department_id: int = Form(...),
    password: str = Form("student123"),
    academic_year: str = Form(None),
    section: str = Form(None),
    roll_number: str = Form(None),
    phone_number: str = Form(None),
    photos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    student = _create_student_user(db, username, email, full_name, department_id, password,
                                   academic_year, section, roll_number, phone_number)
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

    _save_embedding_and_samples(db, student, frames)
    _log_event(db, "enroll_student", f"Enrolled student: {full_name}", user.id)
    return {"id": student.id, "email": email, "full_name": full_name, "enrolled": True}


class EnrollWebcamRequest(BaseModel):
    username: str
    email: str
    full_name: str
    department_id: int
    password: str = "student123"
    academic_year: Optional[str] = None
    section: Optional[str] = None
    roll_number: Optional[str] = None
    phone_number: Optional[str] = None
    frames_base64: List[str]


@router.post("/students/enroll-webcam")
def enroll_student_webcam(
    req: EnrollWebcamRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    student = _create_student_user(db, req.username, req.email, req.full_name, req.department_id, req.password,
                                   req.academic_year, req.section, req.roll_number, req.phone_number)

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

    _save_embedding_and_samples(db, student, frames, req.frames_base64)
    _log_event(db, "enroll_student", f"Enrolled student via webcam: {req.full_name}", user.id)
    return {"id": student.id, "email": req.email, "full_name": req.full_name, "enrolled": True}


# ---------- Dashboard KPIs ----------

@router.get("/dashboard/kpis")
def dashboard_kpis(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    total_students = db.query(Student).count()
    total_teachers = db.query(User).filter(User.role == Role.teacher).count()

    today = date_type.today()
    today_start = datetime(today.year, today.month, today.day)
    today_end = today_start + timedelta(days=1)

    today_records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.date >= today_start, AttendanceRecord.date < today_end)
        .all()
    )

    todays_logs = len(today_records)
    present_today = sum(1 for r in today_records if r.status in (AttendanceStatus.present, AttendanceStatus.late))
    absent_today = sum(1 for r in today_records if r.status == AttendanceStatus.absent)
    rate = round((present_today / todays_logs) * 100, 1) if todays_logs else 0.0

    return {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "todays_logs": todays_logs,
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_rate": rate,
    }


# ---------- Activity Stream ----------

@router.get("/activity-stream")
def activity_stream(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    events = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "user": e.user.full_name if e.user else "System",
            "action": e.action,
            "details": e.details,
            "category": e.category.value,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]


# ---------- Attendance Records (global admin view) ----------

@router.get("/attendance/records")
def admin_attendance_records(
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    status: Optional[str] = None,
    date_on: Optional[date_type] = None,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    query = (
        db.query(AttendanceRecord)
        .join(Student, Student.id == AttendanceRecord.student_id)
        .join(User, User.id == Student.user_id)
    )
    if department_id:
        query = query.filter(Student.department_id == department_id)
    if status:
        query = query.filter(AttendanceRecord.status == status)
    if date_on:
        day_start = datetime(date_on.year, date_on.month, date_on.day)
        day_end = day_start + timedelta(days=1)
        query = query.filter(AttendanceRecord.date >= day_start, AttendanceRecord.date < day_end)
    if search:
        query = query.filter(User.full_name.ilike(f"%{search}%"))

    records = query.order_by(AttendanceRecord.date.desc()).limit(500).all()

    CAMERA_LABELS = {
        "cam-001": "Main Kiosk Terminal #1",
        "cam-002": "Main Kiosk Terminal #2",
    }

    return [
        {
            "id": r.id,
            "student_id": r.student.user.username,
            "full_name": r.student.user.full_name,
            "department": r.student.department.name,
            "date": r.date.isoformat() if r.date else None,
            "status": r.status.value,
            "confidence": r.recognition_confidence,
            "terminal": CAMERA_LABELS.get(
                r.timetable_entry.room if r.timetable_entry else None,
                r.timetable_entry.room if r.timetable_entry else "Unknown"
            ),
        }
        for r in records
    ]


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


# ---------- Reports / Export ----------

@router.get("/reports/preview")
def reports_preview(
    department_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    query = db.query(AttendanceRecord).join(Student, Student.id == AttendanceRecord.student_id)
    if department_id:
        query = query.filter(Student.department_id == department_id)
    if date_from:
        query = query.filter(AttendanceRecord.date >= datetime(date_from.year, date_from.month, date_from.day))
    if date_to:
        day_end = datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
        query = query.filter(AttendanceRecord.date < day_end)

    records = query.order_by(AttendanceRecord.date.desc()).all()
    total = len(records)
    present = sum(1 for r in records if r.status in (AttendanceStatus.present,))
    late = sum(1 for r in records if r.status == AttendanceStatus.late)
    absent = sum(1 for r in records if r.status == AttendanceStatus.absent)
    turnout = round(((present + late) / total) * 100, 1) if total else 0.0

    preview_rows = [
        {
            "student_name": r.student.user.full_name,
            "department": r.student.department.name,
            "date": r.date.date().isoformat() if r.date else "",
            "status": r.status.value,
            "confidence": r.recognition_confidence,
        }
        for r in records[:10]
    ]

    return {
        "total_logged": total,
        "present": present,
        "late": late,
        "absent": absent,
        "turnout_rate": turnout,
        "preview": preview_rows,
    }


@router.get("/reports/attendance/export")
def export_attendance(
    format: str = "csv",
    department_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    query = db.query(AttendanceRecord).join(Student, Student.id == AttendanceRecord.student_id)
    if department_id:
        query = query.filter(Student.department_id == department_id)
    if date_from:
        query = query.filter(AttendanceRecord.date >= datetime(date_from.year, date_from.month, date_from.day))
    if date_to:
        day_end = datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
        query = query.filter(AttendanceRecord.date < day_end)

    records = query.order_by(AttendanceRecord.date.desc()).all()

    headers = ["Student Name", "Email", "Department", "Date", "Status", "Entry Time", "Exit Time", "Confidence", "Corrected"]

    def row_data(r):
        return [
            r.student.user.full_name, r.student.user.email, r.student.department.name,
            r.date.date().isoformat() if r.date else "", r.status.value,
            r.entry_time.isoformat() if r.entry_time else "",
            r.exit_time.isoformat() if r.exit_time else "",
            str(r.recognition_confidence) if r.recognition_confidence is not None else "",
            "Yes" if r.is_corrected else "No",
        ]

    if format == "xlsx":
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(status_code=500, detail="openpyxl not installed")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Attendance"
        ws.append(headers)
        for r in records:
            ws.append(row_data(r))
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=attendance_report.xlsx"},
        )

    elif format == "pdf":
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib import colors
        except ImportError:
            raise HTTPException(status_code=500, detail="reportlab not installed")

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elements = []
        elements.append(Paragraph("Attendance Report", styles['Title']))
        elements.append(Spacer(1, 12))

        table_data = [headers]
        for r in records[:200]:  # limit rows for PDF
            table_data.append(row_data(r))

        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a7dff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        elements.append(t)
        doc.build(elements)
        buf.seek(0)
        return StreamingResponse(
            buf, media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=attendance_report.pdf"},
        )

    else:  # CSV default
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for r in records:
            writer.writerow(row_data(r))
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=attendance_report.csv"},
        )


# ---------- Analytics summary ----------

@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    total_students = db.query(Student).count()
    total_teachers = db.query(User).filter(User.role == Role.teacher).count()
    total_departments = db.query(Department).count()

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

    department_breakdown = []
    for dept in db.query(Department).all():
        dept_students = db.query(Student).filter(Student.department_id == dept.id).count()
        dept_records = (
            db.query(AttendanceRecord)
            .join(Student, Student.id == AttendanceRecord.student_id)
            .filter(Student.department_id == dept.id)
            .all()
        )
        dept_total = len(dept_records)
        dept_present = sum(
            1 for r in dept_records
            if r.status in (AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.left_early)
        )
        department_breakdown.append({
            "department": dept.name,
            "student_count": dept_students,
            "total_records": dept_total,
            "attendance_rate": round((dept_present / dept_total) * 100, 1) if dept_total else 0.0,
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
            "total": day_total,
            "present": day_present,
            "attendance_rate": round((day_present / day_total) * 100, 1) if day_total else 0.0,
        })

    # Today's turnout for doughnut chart
    today_start = datetime(today.year, today.month, today.day)
    today_end = today_start + timedelta(days=1)
    today_records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.date >= today_start, AttendanceRecord.date < today_end)
        .all()
    )
    today_present = sum(1 for r in today_records if r.status in (AttendanceStatus.present, AttendanceStatus.late))
    today_absent = sum(1 for r in today_records if r.status == AttendanceStatus.absent)

    return {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_departments": total_departments,
        "status_counts": status_counts,
        "overall_attendance_rate": overall_rate,
        "department_breakdown": department_breakdown,
        "trend_last_7_days": trend,
        "today_present": today_present,
        "today_absent": today_absent,
    }


# ---------- Backup / Restore ----------

@router.get("/backup/export")
def backup_export(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Serialize all tables to a single JSON file download."""
    data = {
        "departments": [{"id": d.id, "name": d.name} for d in db.query(Department).all()],
        "users": [
            {"id": u.id, "username": u.username, "email": u.email,
             "hashed_password": u.hashed_password, "full_name": u.full_name,
             "role": u.role.value, "created_at": u.created_at.isoformat() if u.created_at else None}
            for u in db.query(User).all()
        ],
        "students": [
            {"id": s.id, "user_id": s.user_id, "department_id": s.department_id,
             "academic_year": s.academic_year, "section": s.section,
             "roll_number": s.roll_number, "phone_number": s.phone_number}
            for s in db.query(Student).all()
        ],
        "enrolled_faces": [
            {"id": f.id, "student_id": f.student_id, "embedding": f.embedding,
             "enrolled_at": f.enrolled_at.isoformat() if f.enrolled_at else None}
            for f in db.query(EnrolledFace).all()
        ],
        "timetable_entries": [
            {"id": e.id, "department_id": e.department_id, "teacher_id": e.teacher_id,
             "subject": e.subject, "room": e.room, "day_of_week": e.day_of_week,
             "start_time": e.start_time.isoformat(), "end_time": e.end_time.isoformat(),
             "late_grace_minutes": e.late_grace_minutes,
             "early_exit_buffer_minutes": e.early_exit_buffer_minutes}
            for e in db.query(TimetableEntry).all()
        ],
    }
    content = json.dumps(data, indent=2)
    buf = io.BytesIO(content.encode('utf-8'))
    _log_event(db, "backup_export", "Full database backup exported", user.id, AuditEventCategory.system)
    return StreamingResponse(
        buf, media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=smartface_backup.json"},
    )


@router.post("/backup/restore")
def backup_restore(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Restore database from a JSON backup. WARNING: this wipes all existing data."""
    try:
        content = file.file.read()
        data = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON backup file")

    from database import engine, Base
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Re-populate from backup
    for d in data.get("departments", []):
        db.add(Department(id=d["id"], name=d["name"]))
    db.flush()

    for u in data.get("users", []):
        db.add(User(id=u["id"], username=u["username"], email=u["email"],
                    hashed_password=u["hashed_password"], full_name=u["full_name"],
                    role=Role(u["role"])))
    db.flush()

    for s in data.get("students", []):
        db.add(Student(id=s["id"], user_id=s["user_id"], department_id=s["department_id"],
                       academic_year=s.get("academic_year"), section=s.get("section"),
                       roll_number=s.get("roll_number"), phone_number=s.get("phone_number")))
    db.flush()

    for f in data.get("enrolled_faces", []):
        db.add(EnrolledFace(id=f["id"], student_id=f["student_id"], embedding=f["embedding"]))
    db.flush()

    for e in data.get("timetable_entries", []):
        db.add(TimetableEntry(
            id=e["id"], department_id=e["department_id"], teacher_id=e["teacher_id"],
            subject=e["subject"], room=e["room"], day_of_week=e["day_of_week"],
            start_time=_parse_time(e["start_time"]), end_time=_parse_time(e["end_time"]),
            late_grace_minutes=e.get("late_grace_minutes", 10),
            early_exit_buffer_minutes=e.get("early_exit_buffer_minutes", 10),
        ))

    db.commit()
    _log_event(db, "backup_restore", "Database restored from backup", user.id, AuditEventCategory.system)
    return {"detail": "Backup restored successfully"}


# ---------- Admin Password Change ----------

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(req.new_password)
    db.commit()
    _log_event(db, "change_password", "Admin changed their password", user.id, AuditEventCategory.system)
    return {"detail": "Password changed successfully"}
