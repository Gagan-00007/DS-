# Project 3: Classroom Attendance via Door-Checkpoint Face Recognition

> This document is written to be handed directly to an AI coding assistant (Claude Code, Antigravity, etc.) as a build spec. It includes architecture, data contracts, and step-by-step tasks.

---

## 1. What we're building

A classroom attendance system built around **two door-mounted cameras** (entry-facing and exit-facing) instead of a continuous wide-angle classroom feed, with an optional third **board-mounted camera** for a secondary, identity-free headcount check (see Stretch Goals, section 7). Students are recognized as they pass through the door; the system cross-references the timetable to know which class/section is active and marks each enrolled student present, late, left-early, or absent accordingly. Students log in to see their own attendance; teachers log in to see and correct their class's attendance and get notified when a student's monthly absences cross a threshold.

**Why door checkpoints, not a classroom-wide camera:** face recognition accuracy drops sharply with distance, angle, and lighting — a camera mounted to view an entire room would produce a lot of `unrecognized` results from back rows and side angles, which isn't reliable for a live demo or real use. A door checkpoint gives close-range, front-facing, well-lit face captures, which is what the recognition model is actually good at. This also means **blink-based liveness detection stays relevant** — someone could plausibly hold up a photo at a close-range door checkpoint to proxy-checkin for a friend, which wasn't a realistic threat in a wide classroom shot.

**Note on what's "AI" here (be precise for judges):** face **recognition** is genuinely AI/ML — the embeddings come from a trained neural network and matching is a learned embedding-space comparison. Blink-based **liveness** (EAR) is classical computer vision — deterministic geometry and a threshold, not a trained classifier (though the landmark detector underneath is a trained model). The **absence-notification job** and **timetable matching** are plain business logic, not AI. Lead with recognition when asked "what's the AI here."

**Note on shared project backbone:** if the shared LangChain + OmniRoute agent backend and common phone-accessible dashboard (used across the rover and arm projects) are still the plan, this project's frontend/backend should be wired into that shared layer rather than built as an island — flag this before starting implementation.

---

## 2. System Architecture

```
[Entry Camera @ Door]          [Exit Camera @ Door]
   |                                |
   | frame bursts                  | frame bursts
   v                                v
        [Backend Server - FastAPI, Python]
        |-- POST /checkpoint/scan  <- entry or exit event, runs recognition + liveness
        |-- GET  /attendance/log   <- attendance history (role-scoped)
        |-- PATCH /attendance/{id} <- teacher correction, writes audit trail
        |-- GET  /timetable        <- active class/section/room for current time
        |-- POST /auth/login       <- student / teacher / admin login
        |
        |-- Face Detection + Recognition (face_recognition / OpenCV, roster-scoped)
        |-- Liveness Check (blink detection)
        |-- Timetable Engine (which class is active, which roster to match against)
        |-- Attendance Store (SQLite) + Audit Log
        |-- Monthly Absence Job (scheduled) -> Notification Service
                |
                v
        [Web Dashboard]
        |-- Student view: own attendance record only
        |-- Teacher view: class roster attendance, correction UI, notifications
        |-- Admin view: enrollment, timetable setup, user/role management
```

---

## 3. Component Breakdown

### 3.1 Enrollment (do this first, before the hackathon demo)

- Collect 2–3 reference photos per student (different angles/lighting).
- Compute and store a face embedding for each student using the recognition library, keyed by student ID.
- Store these in a simple local file/DB (e.g. `enrolled_faces.pkl` or a small SQLite table) — this is a one-time setup script, not part of the live demo flow.
- Link each enrolled face to a student account (for login) and a section/class roster (so recognition only needs to match against that section's students, not the whole school — smaller candidate pool, better accuracy).

**File to create:** `backend/enroll.py` (run once per student, offline, before the event)

---

### 3.2 Auth + Roles

**Roles:**
- **Student:** logs in, sees only their own attendance record and history. Cannot see other students' data or edit anything.
- **Teacher:** logs in, sees attendance for the classes/sections they teach, can correct entries (with reason required), receives absence-threshold notifications for their students.
- **Admin:** manages enrollment, timetable, and user/role assignment. (Can be you/organizers for the demo — doesn't need to be a polished UI, a simple seed script is fine for a hackathon.)

**Approach for a hackathon timeline:** simple email/username + password auth with a role field on the user record and route-level checks (`if user.role != "teacher": 403`) is enough — don't build a full permissions framework. JWT or session cookies, whichever is faster to wire up with FastAPI.

**Files to create:**
- `backend/auth.py` (login, password hashing, role check dependency)
- `backend/models/user.py` (student/teacher/admin user model with role field)

---

### 3.3 Timetable Engine

- A table of `(section, subject, teacher_id, room, day_of_week, start_time, end_time)`.
- Given a checkpoint event's timestamp, the engine resolves **which class is currently active for that door/room**, which tells the system:
  - Which student roster to match recognition against.
  - What "on time" vs "late" means (start_time + grace period, e.g. 10 min).
  - What "present" requires (an entry event with no corresponding "left early" flag).
- Also exposed via `GET /timetable` so the dashboard can show "Class 10-B, Physics, 10:00–10:50" live.

**Files to create:**
- `backend/timetable.py` (lookup: given room + timestamp, return active class/section/roster)
- `backend/models/timetable.py`

---

### 3.4 Checkpoint Pipeline (Entry + Exit)

**Endpoint:** `POST /checkpoint/scan` — same endpoint for both cameras, distinguished by a `checkpoint_type: "entry" | "exit"` field and a `camera_id`.

**Pipeline:**
1. **Resolve active class:** look up the timetable for this room/camera at the current timestamp. If no class is active, return `{"status": "no_active_class"}`.
2. **Face detection:** locate face(s) in the frame burst. If none found, return `{"status": "no_face"}`.
3. **Face recognition:** match against the **active class's roster only** (not the whole school), for accuracy and speed. If no match above threshold, return `{"status": "unrecognized"}`.
4. **Liveness check (blink detection):** as in the original design — EAR across a frame burst, catches static photo spoofing. If no blink pattern, return `{"status": "spoof_suspected"}`.
5. **If recognized AND live:**
   - `checkpoint_type: "entry"` → log an entry event with timestamp. Compare against class `start_time` to compute `on_time` vs `late`.
   - `checkpoint_type: "exit"` → log an exit event with timestamp. If this exit is well before class `end_time` (minus a small buffer), flag the student's status as `left_early` instead of `present`.
6. Every outcome (including spoof attempts) gets written to the log — useful for both the demo narrative and a "security events" view.

**End-of-period status resolution (can run as each exit event lands, or as a small job at `end_time`):**
- Entry event present + no early exit → **present** (or **late**, per step 5).
- Entry event present + early exit flagged → **left_early**.
- No entry event at all for an enrolled student in that period → **absent**.

**Files to create:**
- `backend/main.py` (FastAPI app + endpoints)
- `backend/recognition.py` (face detection + roster-scoped matching)
- `backend/liveness.py` (blink detection via EAR across frame sequence)
- `backend/checkpoint.py` (entry/exit event handling, status resolution logic)
- `backend/attendance_store.py` (SQLite read/write helpers)
- `backend/requirements.txt`

---

### 3.5 Attendance Correction Workflow (Teacher)

- Teachers can view their class's attendance for any period and correct a status (e.g. a student was actually present but got flagged `unrecognized` due to lighting).
- **Every correction requires a reason** (free text, e.g. "recognized manually, camera angle issue") and is written to an **audit log**, not just overwritten — keep the original system-generated value alongside the corrected value and who changed it, so there's a trail if a correction is disputed later.
- `PATCH /attendance/{id}` — body: `{"new_status": "...", "reason": "...", "corrected_by": teacher_id}`.

**Files to create:**
- `backend/models/audit_log.py`
- Extend `backend/attendance_store.py` with correction + audit read/write helpers

---

### 3.6 Monthly Absence Notification

- A scheduled job (daily or weekly is fine for a demo — doesn't need to be real-time) recalculates each student's absence count for the current month.
- If a student's absence count exceeds **7 for the month**, generate a notification for the teacher(s) of the sections that student is enrolled in.
- **Notification delivery — pick one for the demo, keep it simple:** an in-app notification badge/list on the teacher dashboard is the fastest to build and demo reliably; email (via a simple SMTP or a service like SendGrid) is a good stretch goal if time allows. Don't try to build both under time pressure — get one working end-to-end first.
- Notifications should be **dismissible but not silently lost** — mark as read, don't delete, so there's a record the teacher was notified.

**Files to create:**
- `backend/notifications.py` (threshold check + notification creation)
- `backend/jobs/monthly_absence_check.py` (scheduled job — can be triggered via a simple cron-like scheduler such as APScheduler, or manually triggered via a button for demo purposes)

---

### 3.7 Frontend — Dashboard (`/frontend`)

**Tech:** Plain HTML/CSS/JS, consistent with the other projects' dashboard style.

**Views (role-gated after login):**
- **Student view:** own attendance history (present/late/absent/left-early per period), simple calendar or table layout.
- **Teacher view:** class/section attendance table for a selected date/period, correction controls per entry, notifications panel for students crossing the absence threshold.
- **Checkpoint camera view** (runs on the phone/device mounted at the door, not a login-based view): live `<video>` feed, status text through pipeline stages (`Idle` → `Face Detected` → `Verifying Liveness...` → `✅ Marked <status>: <name>` or `❌ Spoof Attempt Detected`), same as the original single-scan design but running continuously or on a short interval rather than button-press, since it needs to catch students passing through without requiring each one to stop and tap a button.

**Files to create:**
- `frontend/index.html` / `frontend/login.html`
- `frontend/checkpoint.js` (camera capture + scan loop, runs on the door devices)
- `frontend/student-dashboard.js`
- `frontend/teacher-dashboard.js`
- `frontend/style.css`

---

## 4. Build Order (recommended sequence)

1. **Enrollment script first:** photos + embeddings per student, linked to a section roster. Get this working reliably before anything else.
2. **Timetable engine:** static seed data (a few classes/sections/time slots) and the lookup logic — everything downstream depends on knowing "what class is active right now."
3. **Basic entry-checkpoint recognition, no liveness:** `/checkpoint/scan` with `checkpoint_type: "entry"` — detect + recognize against the active roster, mark present. Get this rock solid first.
4. **Add liveness detection** to the checkpoint pipeline (EAR blink check).
5. **Add exit checkpoint + left-early logic.**
6. **Auth + role-gated dashboards:** student view and teacher view, reading from the attendance store.
7. **Correction workflow** with audit trail.
8. **Monthly absence job + notifications** — can be manually triggered for the demo rather than truly scheduled, to avoid demo-day timing issues.
9. **Test the spoof case explicitly** at the door checkpoint: hold up a phone photo of an enrolled student's face, confirm `spoof_suspected`.
10. **Rehearse the full flow** — entry, late entry, early exit, a correction, and a simulated absence-threshold notification — with different students and lighting conditions at the actual door you'll demo at.

---

## 5. Demo Script (for judges)

1. Show the timetable view — "Class 10-B, Physics is active right now."
2. A student walks through the entry checkpoint — walk through the status states out loud (Face Detected → Verifying Liveness → Marked Present/Late).
3. Demonstrate the anti-proxy check: hold up a phone photo of that same student's face at the checkpoint — show it flagged as a spoof attempt instead of marking attendance.
4. Log in as that student — show they can see their own attendance, nothing else.
5. Log in as the teacher — show the class attendance table, make a correction with a reason, show the audit trail.
6. Trigger the monthly absence job manually — show a notification appearing for a student seeded with 8+ absences.
7. Be upfront about scope if asked: recognition works best at close range at the door, which is why it's checkpoint-based rather than a wide classroom camera; blink-based liveness catches static photos but not video replay, which would need a further layer (e.g. challenge-response) as a next step.

---

## 6. Known Risks / Things to Test Early

- Lighting at the actual door you'll demo at — test there specifically, not just anywhere.
- Two students entering close together at the checkpoint — decide and test how the frame-burst capture handles multiple faces in frame (queue them, or require one-at-a-time — simplest for a demo is one-at-a-time).
- False rejections (a real student not recognized) are more embarrassing live than false acceptances — tune the similarity threshold conservatively, test each enrolled student multiple times.
- Timetable edge cases: what happens right at a period boundary, or if two classes are scheduled in the same room back-to-back — decide the grace-period behavior early, don't leave it ambiguous until demo day.
- `enrolled_faces.pkl` and any student PII contain biometric/personal data — gitignore it, never commit to a public repo, even a hackathon throwaway one.
- Correction audit trail: make sure a correction can't be corrected again silently — every change should append to history, not overwrite it.

---

## 7. Stretch Goals (only after core flow is solid and rehearsed)

- **Challenge-response liveness:** a second randomized liveness signal (e.g. "turn your head left") layered on top of blink detection, addressing the video-replay gap noted in section 5.
- **Client-side inference:** move recognition + liveness into the browser with `face-api.js` (TensorFlow.js) on the checkpoint devices, matching the client-side detection approach used in the rover/arm projects — cuts round-trip latency.
- **Email notifications** in addition to in-app, once the in-app version is solid.
- **Parent-facing view:** read-only attendance visibility for a student's guardian, if there's time and it fits the scope of the event.
- **Board camera — occupancy/headcount cross-check (generic person tracking, not identity):** a third camera mounted with a wide view of the room, running a person detector (e.g. YOLO) + a multi-object tracker (e.g. ByteTrack/DeepSORT-style) to assign each visible person a temporary tracking ID and follow it frame-to-frame — similar to vehicle-counting systems that box and number each vehicle in a traffic feed. This does **not** identify who anyone is; it only tracks generic "person shapes" and counts how many are in the room or crossing a zone near the exit.
  - **What it's good for:** a rough live headcount to sanity-check the door checkpoints — e.g. "30 students checked in, but the room shows 27 people mid-class" flags that someone may have left through a side door or a checkpoint scan silently failed.
  - **What it can't do:** tell you *which* student the missing count is — that requires stitching a tracking ID back to a recognized identity from the door cameras, which is a real fusion problem (tracking IDs commonly swap or get lost when people cross paths, a known failure mode of this technique, not something to assume away).
  - **Scope honestly for judges:** present this as "secondary occupancy verification," not as a replacement for the exit checkpoint's identity-resolved attendance data — the exit camera remains the source of truth for *who* left.
  - Only take this on after the core checkpoint + auth + timetable + correction + notification flow (sections 3.1–3.6) is fully working and rehearsed — it's a meaningful subsystem in its own right (detector + tracker + zone-crossing counter), not a quick add-on, despite looking simple in reference footage.
