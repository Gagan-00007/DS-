"""
Self-contained dry-run script testing all 13 core steps of the Classroom Attendance system.
Uses starlette.testclient (TestClient) against the FastAPI app in `main.py`.
"""

import sys
import os
import json
import base64
import numpy as np
from datetime import datetime
from starlette.testclient import TestClient

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import main
import recognition
import liveness
import timetable
from database import SessionLocal
from models import SecurityEvent, SecurityEventType

client = TestClient(main.app)

def run_dry_run():
    print("\n=======================================================")
    print("      CLASSROOM ATTENDANCE SYSTEM - 14 STEP DRY RUN      ")
    print("=======================================================\n")
    
    passed_steps = 0
    failed_steps = 0

    def print_result(step_num, title, success, detail=""):
        nonlocal passed_steps, failed_steps
        if success:
            passed_steps += 1
            print(f"Step {step_num:02d}: [PASS] {title}")
            if detail:
                print(f"         {detail}")
        else:
            failed_steps += 1
            print(f"Step {step_num:02d}: [FAIL] {title}")
            if detail:
                print(f"         Error: {detail}")

    asha_embedding_path = os.path.join(backend_dir, "asha_synthetic_embedding.json")
    if not os.path.exists(asha_embedding_path):
        print(f"ERROR: {asha_embedding_path} not found. Please run seed.py first!")
        sys.exit(1)

    with open(asha_embedding_path, "r") as f:
        asha_embedding_vec = np.array(json.load(f))

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    import cv2
    _, img_encoded = cv2.imencode(".jpg", dummy_img)
    b64_frame = base64.b64encode(img_encoded).decode("utf-8")

    tokens = {}

    res1 = client.get("/docs")
    print_result(1, "Backend Health (GET /docs)", res1.status_code == 200, f"Status code: {res1.status_code}")

    res2 = client.post("/auth/login", data={"username": "admin@school.edu", "password": "admin123"})
    if res2.status_code == 200 and "access_token" in res2.json():
        tokens["admin"] = res2.json()["access_token"]
        print_result(2, "Admin Login", True, f"Token obtained for role: {res2.json().get('role')}")
    else:
        print_result(2, "Admin Login", False, res2.text)

    res3 = client.post("/auth/login", data={"username": "teacher.physics@school.edu", "password": "teacher123"})
    if res3.status_code == 200 and "access_token" in res3.json():
        tokens["teacher"] = res3.json()["access_token"]
        print_result(3, "Teacher Login", True, f"Token obtained for role: {res3.json().get('role')}")
    else:
        print_result(3, "Teacher Login", False, res3.text)

    res4 = client.post("/auth/login", data={"username": "asha@school.edu", "password": "student123"})
    if res4.status_code == 200 and "access_token" in res4.json():
        tokens["student"] = res4.json()["access_token"]
        print_result(4, "Student Login", True, f"Token obtained for role: {res4.json().get('role')}")
    else:
        print_result(4, "Student Login", False, res4.text)

    res5 = client.get("/timetable/active?room=ROOM-101")
    if res5.status_code == 200 and res5.json().get("active"):
        data5 = res5.json()
        print_result(5, "Active Timetable Lookup", True, f"Room ROOM-101 active for section {data5.get('section')} ({data5.get('subject')})")
    else:
        print_result(5, "Active Timetable Lookup", False, res5.text)

    orig_extract = recognition._extract_embedding
    orig_liveness = liveness.detect_blink
    
    recognition._extract_embedding = lambda frame: asha_embedding_vec
    liveness.detect_blink = lambda frames: True

    res6 = client.post("/checkpoint/scan", json={
        "room": "ROOM-101",
        "camera_id": "CAM-01",
        "checkpoint_type": "entry",
        "frames_base64": [b64_frame, b64_frame, b64_frame]
    })
    
    if res6.status_code == 200 and res6.json().get("status") in ("marked_present", "marked_late"):
        data6 = res6.json()
        print_result(6, "Entry Checkpoint Scan", True, f"Student {data6.get('student_name')} -> status: {data6.get('status')}")
    else:
        print_result(6, "Entry Checkpoint Scan", False, res6.text)

    headers_student = {"Authorization": f"Bearer {tokens.get('student')}"}
    res7 = client.get("/attendance/me", headers=headers_student)
    if res7.status_code == 200 and isinstance(res7.json(), list) and len(res7.json()) > 0:
        records = res7.json()
        print_result(7, "Student Attendance Retrieval", True, f"Retrieved {len(records)} record(s) for Asha")
    else:
        print_result(7, "Student Attendance Retrieval", False, res7.text)

    headers_teacher = {"Authorization": f"Bearer {tokens.get('teacher')}"}
    res8 = client.get("/attendance/section/1", headers=headers_teacher)
    corrected_record_id = None
    if res8.status_code == 200 and isinstance(res8.json(), list) and len(res8.json()) > 0:
        records8 = res8.json()
        corrected_record_id = records8[0]["id"]
        print_result(8, "Section Attendance Retrieval", True, f"Retrieved {len(records8)} section record(s)")
    else:
        print_result(8, "Section Attendance Retrieval", False, res8.text)

    if corrected_record_id:
        res9 = client.patch(
            f"/attendance/{corrected_record_id}",
            headers=headers_teacher,
            json={"new_status": "present", "reason": "Manual verification during dry run"}
        )
        if res9.status_code == 200 and res9.json().get("is_corrected"):
            print_result(9, "Teacher Attendance Correction", True, f"Record {corrected_record_id} updated to status 'present'")
        else:
            print_result(9, "Teacher Attendance Correction", False, res9.text)
    else:
        print_result(9, "Teacher Attendance Correction", False, "No attendance record ID available to correct")

    if corrected_record_id:
        res10 = client.get(f"/attendance/{corrected_record_id}/audit", headers=headers_teacher)
        if res10.status_code == 200 and isinstance(res10.json(), list) and len(res10.json()) > 0:
            audit_entry = res10.json()[0]
            print_result(10, "Audit Trail Inspection", True, f"Audit log verified: changed by {audit_entry.get('changed_by')} (Reason: '{audit_entry.get('reason')}')")
        else:
            print_result(10, "Audit Trail Inspection", False, res10.text)
    else:
        print_result(10, "Audit Trail Inspection", False, "No attendance record ID available for audit trail")

    headers_admin = {"Authorization": f"Bearer {tokens.get('admin')}"}
    res11 = client.post("/notifications/run-monthly-check", headers=headers_admin)
    if res11.status_code == 200 and res11.json().get("notifications_created", 0) >= 1:
        print_result(11, "Monthly Check Trigger", True, f"Triggered check: {res11.json().get('notifications_created')} notification(s) created")
    else:
        print_result(11, "Monthly Check Trigger", False, res11.text)

    res12 = client.get("/notifications/me", headers=headers_teacher)
    if res12.status_code == 200 and isinstance(res12.json(), list) and len(res12.json()) > 0:
        notif = res12.json()[0]
        print_result(12, "Teacher Notifications Check", True, f"Notification received for student {notif.get('student_name')}: '{notif.get('message')}'")
    else:
        print_result(12, "Teacher Notifications Check", False, res12.text)

    liveness.detect_blink = lambda frames: False

    res13 = client.post("/checkpoint/scan", json={
        "room": "ROOM-101",
        "camera_id": "CAM-01",
        "checkpoint_type": "entry",
        "frames_base64": [b64_frame, b64_frame, b64_frame]
    })

    spoof_ok = False
    spoof_detail = ""
    if res13.status_code == 200 and res13.json().get("status") == "spoof_suspected":
        db = SessionLocal()
        try:
            event = db.query(SecurityEvent).filter(
                SecurityEvent.event_type == SecurityEventType.spoof_suspected
            ).order_by(SecurityEvent.timestamp.desc()).first()
            if event:
                spoof_ok = True
                spoof_detail = f"Status 'spoof_suspected' returned & SecurityEvent logged in DB (ID {event.id}, camera={event.camera_id})"
            else:
                spoof_detail = "Status 'spoof_suspected' returned but SecurityEvent NOT found in database"
        finally:
            db.close()
    else:
        spoof_detail = f"Expected status 'spoof_suspected', got response: {res13.text}"

    print_result(13, "Spoof Detection Check", spoof_ok, spoof_detail)

    # Step 14: ROOM-102 Late Detection (regression test for the on-time vs
    # late seed scenario — no roster exists in section 10-C, so this checks
    # the timetable engine's is_late() logic directly rather than a full
    # checkpoint scan, which would fail on recognition for an unrelated reason).
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        active_102 = timetable.get_active_class(db, room="ROOM-102", at=now)
        if active_102 is None:
            print_result(14, "ROOM-102 Late Detection", False, "No active class found for ROOM-102")
        else:
            is_late_102 = timetable.is_late(active_102, now)
            if is_late_102:
                print_result(14, "ROOM-102 Late Detection", True,
                              f"ROOM-102 ({active_102.subject}) correctly resolves as late "
                              f"(grace={active_102.late_grace_minutes}min)")
            else:
                print_result(14, "ROOM-102 Late Detection", False,
                              f"Expected late=True, got False for ROOM-102 ({active_102.subject})")
    finally:
        db.close()

    recognition._extract_embedding = orig_extract
    liveness.detect_blink = orig_liveness

    print("\n=======================================================")
    print(f"  DRY RUN RESULTS: {passed_steps}/14 PASSED, {failed_steps}/14 FAILED")
    print("=======================================================\n")

    if failed_steps > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_dry_run()
