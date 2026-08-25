"""
FastAPI app — wires together auth, timetable, checkpoint pipeline,
attendance store, and notifications into the HTTP API the frontend calls.

Run with: uvicorn main:app --reload
"""

import base64
import io
from datetime import date as date_type
from typing import List, Optional

import cv2
import numpy as np
import os
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import attendance_store
import checkpoint
import notifications
import timetable as timetable_engine
from database import get_db, init_db
from models import Role, User, AttendanceStatus

app = FastAPI(title="Classroom Attendance API")

# Wide open for hackathon dev — tighten allow_origins before any real deployment.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path, html=True), name="frontend")

@app.get("/")
def root():
    login_file = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_file):
        return FileResponse(login_file)
    return RedirectResponse(url="/docs")


@app.on_event("startup")
def on_startup():
    init_db()


# ---------- Schemas ----------

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


class CheckpointScanRequest(BaseModel):
    room: str
    camera_id: str
    checkpoint_type: str  # "entry" | "exit"
    frames_base64: List[str]  # base64-encoded JPEG/PNG frames from the burst


class CheckpointScanResponse(BaseModel):
    status: str
    student_name: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[str] = None


class CorrectionRequest(BaseModel):
    new_status: AttendanceStatus
    reason: str


# ---------- Auth ----------

@app.post("/auth/login", response_model=LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = auth.create_access_token(user)
    return LoginResponse(access_token=token, role=user.role.value, full_name=user.full_name)


# ---------- Checkpoint (called by door camera devices, not login-gated) ----------

def _decode_frames(frames_base64: List[str]) -> List[np.ndarray]:
    frames = []
    for b64_str in frames_base64:
        img_bytes = base64.b64decode(b64_str)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame_bgr is not None:
            frames.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    return frames


@app.post("/checkpoint/scan", response_model=CheckpointScanResponse)
def checkpoint_scan(req: CheckpointScanRequest, db: Session = Depends(get_db)):
    if req.checkpoint_type not in ("entry", "exit"):
        raise HTTPException(status_code=400, detail="checkpoint_type must be 'entry' or 'exit'")

    frames = _decode_frames(req.frames_base64)
    if not frames:
        raise HTTPException(status_code=400, detail="No decodable frames in request")

    result = checkpoint.run_checkpoint_pipeline(
        db, frames=frames, room=req.room, camera_id=req.camera_id,
        checkpoint_type=req.checkpoint_type,
    )
    return CheckpointScanResponse(
        status=result.status, student_name=result.student_name,
        confidence=result.confidence, timestamp=result.timestamp,
    )


# ---------- Timetable ----------

@app.get("/timetable/active")
def active_class(room: str, db: Session = Depends(get_db)):
    entry = timetable_engine.get_active_class(db, room=room)
    if entry is None:
        return {"active": False}
    return {
        "active": True,
        "section": entry.section.name,
        "subject": entry.subject,
        "room": entry.room,
        "start_time": entry.start_time.isoformat(),
        "end_time": entry.end_time.isoformat(),
    }


# ---------- Attendance (role-gated) ----------

@app.get("/attendance/me")
def my_attendance(
    user: User = Depends(auth.require_role(Role.student)), db: Session = Depends(get_db)
):
    if not user.student_profile:
        raise HTTPException(status_code=404, detail="No student profile linked to this account")
    records = attendance_store.get_attendance_for_student(db, user.student_profile.id)
    return [
        {
            "id": r.id, "date": r.date.isoformat(), "status": r.status.value,
            "entry_time": r.entry_time.isoformat() if r.entry_time else None,
            "exit_time": r.exit_time.isoformat() if r.exit_time else None,
            "is_corrected": r.is_corrected,
        }
        for r in records
    ]


@app.get("/attendance/section/{section_id}")
def section_attendance(
    section_id: int, on_date: Optional[date_type] = None,
    user: User = Depends(auth.require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    records = attendance_store.get_attendance_for_section(db, section_id, on_date)
    return [
        {
            "id": r.id, "student_name": r.student.user.full_name,
            "date": r.date.isoformat(), "status": r.status.value,
            "entry_time": r.entry_time.isoformat() if r.entry_time else None,
            "exit_time": r.exit_time.isoformat() if r.exit_time else None,
            "confidence": r.recognition_confidence, "is_corrected": r.is_corrected,
        }
        for r in records
    ]


@app.patch("/attendance/{record_id}")
def correct_attendance(
    record_id: int, req: CorrectionRequest,
    user: User = Depends(auth.require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    try:
        record = attendance_store.correct_attendance(
            db, record_id, req.new_status, req.reason, corrected_by=user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": record.id, "status": record.status.value, "is_corrected": record.is_corrected}


@app.get("/attendance/{record_id}/audit")
def attendance_audit_trail(
    record_id: int,
    user: User = Depends(auth.require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    trail = attendance_store.get_audit_trail(db, record_id)
    return [
        {
            "changed_by": entry.changed_by.full_name,
            "previous_status": entry.previous_status.value,
            "new_status": entry.new_status.value,
            "reason": entry.reason,
            "changed_at": entry.changed_at.isoformat(),
        }
        for entry in trail
    ]


# ---------- Notifications ----------

@app.get("/notifications/me")
def my_notifications(
    unread_only: bool = False,
    user: User = Depends(auth.require_role(Role.teacher)),
    db: Session = Depends(get_db),
):
    notifs = notifications.get_notifications_for_teacher(db, user.id, unread_only)
    return [
        {
            "id": n.id, "student_name": n.student.user.full_name,
            "message": n.message, "absence_count": n.absence_count,
            "month": n.month, "is_read": n.is_read, "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@app.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: User = Depends(auth.require_role(Role.teacher)),
    db: Session = Depends(get_db),
):
    notification = notifications.mark_notification_read(db, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"id": notification.id, "is_read": notification.is_read}


@app.post("/notifications/run-monthly-check")
def trigger_monthly_check(
    user: User = Depends(auth.require_role(Role.admin)), db: Session = Depends(get_db)
):
    """Manual trigger for the demo — see spec section 4 on why this beats
    trusting real scheduling to line up with a live demo slot."""
    count = notifications.run_monthly_check_for_all_students(db)
    return {"notifications_created": count}
