"""
Seed script for Classroom Attendance hackathon database.
Populates departments, admin/teacher/student accounts, synthetic enrolled face embeddings,
active timetable entries centered around the current time, and historical absence records.
"""

import os
import json
import numpy as np
from datetime import datetime, time, timedelta

from database import engine, Base, SessionLocal
from models import (
    User, Role, Department, Student, EnrolledFace, EnrolledFaceSample,
    TimetableEntry, AttendanceRecord, AttendanceStatus,
    AuditEvent, AuditEventCategory,
)
from auth import hash_password

def seed_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("=== SEEDING CLASSROOM ATTENDANCE DATABASE ===")

        # 1. Departments
        dept_cs = Department(name='Computer Science')
        dept_me = Department(name='Mechanical Engineering')
        db.add_all([dept_cs, dept_me])
        db.commit()
        db.refresh(dept_cs)
        db.refresh(dept_me)
        print(f"[+] Created Departments: Computer Science (id={dept_cs.id}), Mechanical Engineering (id={dept_me.id})")

        # 2. Admin user
        admin_user = User(
            username='ADMIN-001',
            email='admin@school.edu',
            hashed_password=hash_password('admin123'),
            full_name='System Admin',
            role=Role.admin
        )
        db.add(admin_user)

        # 3. Teachers
        teacher_physics = User(
            username='TCH2026-007',
            email='teacher.physics@school.edu',
            hashed_password=hash_password('teacher123'),
            full_name='Dr. Rajesh Kumar',
            role=Role.teacher
        )
        teacher_chem = User(
            username='TCH2026-008',
            email='teacher.chem@school.edu',
            hashed_password=hash_password('teacher123'),
            full_name='Prof. Meena Iyer',
            role=Role.teacher
        )
        db.add_all([teacher_physics, teacher_chem])
        db.commit()
        print("[+] Created Admin and Teacher accounts")

        # 4. Students with new fields
        student_data = [
            ('1AR24CS000', 'asha@school.edu', 'Asha Sharma', dept_cs.id, '2024-25', 'A', '001', '9876543210'),
            ('1AR24CS001', 'bala@school.edu', 'Bala Kumar', dept_cs.id, '2024-25', 'A', '002', '9876543211'),
            ('1AR24CS002', 'cira@school.edu', 'Cira Gupta', dept_cs.id, '2024-25', 'B', '003', '9876543212'),
            ('1AR24CS003', 'dev@school.edu', 'Dev Patel', dept_cs.id, '2024-25', 'B', '004', '9876543213'),
            ('1AR24ME001', 'ekta@school.edu', 'Ekta Verma', dept_me.id, '2024-25', 'A', '001', '9876543214'),
        ]

        seeded_students = []
        np.random.seed(42)

        for username, email, full_name, dept_id, acad_year, sec, roll, phone in student_data:
            user = User(
                username=username,
                email=email,
                hashed_password=hash_password('student123'),
                full_name=full_name,
                role=Role.student
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            student = Student(
                user_id=user.id, department_id=dept_id,
                academic_year=acad_year, section=sec,
                roll_number=roll, phone_number=phone,
            )
            db.add(student)
            db.commit()
            db.refresh(student)

            raw_vec = np.random.randn(128)
            norm_vec = (raw_vec / np.linalg.norm(raw_vec)).tolist()

            face = EnrolledFace(
                student_id=student.id,
                embedding=json.dumps(norm_vec)
            )
            db.add(face)

            # Seed a synthetic face sample for demo
            sample = EnrolledFaceSample(
                student_id=student.id,
                image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="  # 1x1 transparent PNG placeholder
            )
            db.add(sample)
            db.commit()

            seeded_students.append((user, student, norm_vec))
            print(f"  - Enrolled student {full_name} ({email}) with synthetic 128-d face embedding")

        asha_embedding = seeded_students[0][2]
        with open(os.path.join(os.path.dirname(__file__), 'asha_synthetic_embedding.json'), 'w') as f:
            json.dump(asha_embedding, f)

        # 5. Timetable Entries (active right now)
        now = datetime.utcnow()
        day_of_week = now.weekday()

        start_dt_1 = now - timedelta(minutes=5)
        end_dt_1 = now + timedelta(minutes=90)

        active_entry_1 = TimetableEntry(
            department_id=dept_cs.id,
            teacher_id=teacher_physics.id,
            subject='Physics',
            room='ROOM-101',
            day_of_week=day_of_week,
            start_time=time(start_dt_1.hour, start_dt_1.minute, start_dt_1.second),
            end_time=time(end_dt_1.hour, end_dt_1.minute, end_dt_1.second),
            late_grace_minutes=15,
            early_exit_buffer_minutes=10
        )

        start_dt_2 = now - timedelta(minutes=30)
        end_dt_2 = now + timedelta(minutes=90)

        active_entry_2 = TimetableEntry(
            department_id=dept_me.id,
            teacher_id=teacher_chem.id,
            subject='Chemistry',
            room='ROOM-102',
            day_of_week=day_of_week,
            start_time=time(start_dt_2.hour, start_dt_2.minute, start_dt_2.second),
            end_time=time(end_dt_2.hour, end_dt_2.minute, end_dt_2.second),
            late_grace_minutes=15,
            early_exit_buffer_minutes=10
        )

        db.add_all([active_entry_1, active_entry_2])
        db.commit()
        db.refresh(active_entry_1)
        db.refresh(active_entry_2)
        print(f"[+] Created Active On-Time Timetable Slot: ROOM-101, Dept CS, Physics (ID {active_entry_1.id})")
        print(f"[+] Created Active Late Timetable Slot: ROOM-102, Dept ME, Chemistry (ID {active_entry_2.id})")

        # 6. Historical Absences for Asha (9 records)
        asha_student = seeded_students[0][1]
        absence_count = 0
        for day in range(1, 25):
            try:
                rec_date = datetime(now.year, now.month, day, 10, 0, 0)
                if rec_date < now - timedelta(days=1) and absence_count < 9:
                    abs_rec = AttendanceRecord(
                        student_id=asha_student.id,
                        timetable_entry_id=active_entry_1.id,
                        date=rec_date,
                        status=AttendanceStatus.absent
                    )
                    db.add(abs_rec)
                    absence_count += 1
            except ValueError:
                pass

        db.commit()
        print(f"[+] Seeded {absence_count} historical absence records for Asha in current month ({now.strftime('%Y-%m')})")

        # 7. Seed AuditEvent entries for activity stream demo
        audit_events = [
            AuditEvent(user_id=admin_user.id, category=AuditEventCategory.system,
                       action="system_startup", details="SmartFace AI Engine started successfully"),
            AuditEvent(user_id=admin_user.id, category=AuditEventCategory.user_action,
                       action="login", details="System Admin logged in (admin)"),
            AuditEvent(user_id=admin_user.id, category=AuditEventCategory.user_action,
                       action="enroll_student", details="Enrolled student: Asha Sharma"),
            AuditEvent(user_id=admin_user.id, category=AuditEventCategory.user_action,
                       action="create_teacher", details="Created teacher: Dr. Rajesh Kumar"),
        ]
        db.add_all(audit_events)
        db.commit()
        print("[+] Seeded activity stream audit events")

        print("=== SEED COMPLETE ===")

    finally:
        db.close()

if __name__ == '__main__':
    seed_database()
