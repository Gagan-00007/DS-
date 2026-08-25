# Classroom Attendance — Seed + Dry-Run Implementation Plan

## Overview

Build the seed script (`seed.py`), dry run verification test (`dry_run.py` with 13 steps), and patch date-comparison bugs in `checkpoint.py` and `attendance_store.py`, as well as fixing the Starlette version pin.

## User Review Required

> [!NOTE]
> **No Bypass Code in Production**: As requested, `liveness.py` will remain untouched with zero bypass logic. `dry_run.py` will dynamically monkeypatch `liveness.detect_blink` during test execution (setting it to return `True` for normal flow steps, and `False` for the spoof detection step).

> [!NOTE]
> **Automated Spoof Test (Step 13)**: `dry_run.py` will include Step 13, which sets `liveness.detect_blink` to return `False` during a `/checkpoint/scan` call, asserting that `status` is `"spoof_suspected"` and verifying that a `SecurityEvent` row with `event_type == "spoof_suspected"` is recorded in the database.

---

## Proposed Changes

### Environment & Dependency Pin

#### Starlette Version Compatibility Fix
Install compatible Starlette version:
```bash
python -m pip install "starlette>=0.37,<0.42"
```

---

### Backend Components

#### [MODIFY] [checkpoint.py](file:///c:/Users/Nexus/Documents/Hack-2026/backend/checkpoint.py)
Fix date query against `AttendanceRecord.date` (`DateTime` column) using `datetime` and `timedelta`:

```python
from datetime import datetime, timedelta

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
```

---

#### [MODIFY] [attendance_store.py](file:///c:/Users/Nexus/Documents/Hack-2026/backend/attendance_store.py)
Fix date comparison bugs in `get_absence_count_for_month` and `get_attendance_for_section`:

1. `get_absence_count_for_month`: Use `datetime` objects for month bounds rather than `date` objects:
```python
from datetime import datetime

def get_absence_count_for_month(db: Session, student_id: int, year: int, month: int) -> int:
    start_dt = datetime(year, month, 1)
    if month == 12:
        end_dt = datetime(year + 1, 1, 1)
    else:
        end_dt = datetime(year, month + 1, 1)
        
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.status == AttendanceStatus.absent,
            AttendanceRecord.date >= start_dt,
            AttendanceRecord.date < end_dt,
        )
        .count()
    )
```

2. `get_attendance_for_section`: Handle `on_date` filtering with `datetime` start/end bounds:
```python
from datetime import datetime, timedelta

if on_date:
    day_start = datetime(on_date.year, on_date.month, on_date.day)
    day_end = day_start + timedelta(days=1)
    query = query.filter(AttendanceRecord.date >= day_start, AttendanceRecord.date < day_end)
```

---

#### [NEW] [seed.py](file:///c:/Users/Nexus/Documents/Hack-2026/backend/seed.py)
Creates initial database data:
- Admin user (`admin@school.edu` / `admin123`)
- Teachers (Physics & Chemistry)
- 4 Students in section `10-B` (`asha@school.edu`, etc.)
- Active timetable entry centered on the current time slot for section `10-B` in `ROOM-101`
- 9 historical absent records for `asha@school.edu` in the current month to test absence thresholds
- Synthetic 128-d face embeddings for all test students stored in `enrolled_faces`

---

#### [NEW] [dry_run.py](file:///c:/Users/Nexus/Documents/Hack-2026/backend/dry_run.py)
Automated 13-step test suite using `TestClient` from Starlette/httpx:

1. **Backend health check** (`GET /docs`)
2. **Admin authentication** (`POST /auth/login`)
3. **Teacher authentication** (`POST /auth/login`)
4. **Student authentication** (`POST /auth/login`)
5. **Active timetable lookup** (`GET /timetable/active?room=ROOM-101`)
6. **Entry checkpoint scan** (Monkeypatch `liveness.detect_blink = lambda f: True`, synthetic embedding match)
7. **Student attendance retrieval** (`GET /attendance/me`)
8. **Section attendance retrieval** (`GET /attendance/section/1`)
9. **Teacher attendance correction** (`PATCH /attendance/{id}`)
10. **Audit trail inspection** (`GET /attendance/{id}/audit`)
11. **Monthly absence threshold check execution** (`POST /notifications/run-monthly-check`)
12. **Notification delivery check** (`GET /notifications/me`)
13. **Spoof detection check** (Monkeypatch `liveness.detect_blink = lambda f: False`, verify `status == "spoof_suspected"` and check `SecurityEvent` log entry in DB)

---

## Verification Plan

### Automated Verification
Run the 13-step dry run script:
```bash
cd backend
python seed.py
python dry_run.py
```
Expected output: All 13 steps report `[PASS]`.

### Manual Verification
1. Run server: `uvicorn main:app --reload`
2. Perform login and view dashboards on frontend.
3. Test physical webcam detection / spoofing manually if desired.
