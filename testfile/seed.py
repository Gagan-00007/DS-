"""
Seed script for Classroom Attendance hackathon database.
Populates sections, admin/teacher/student accounts, synthetic enrolled face embeddings,
an active timetable entry centered around the current time, and historical absence records.
"""

import os
import json
import numpy as np
from datetime import datetime, time, timedelta

from database import engine, Base, SessionLocal
from models import (
    User, Role, Section, Student, EnrolledFace, TimetableEntry,
    AttendanceRecord, AttendanceStatus
)
from auth import hash_password

def seed_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        print("=== SEEDING CLASSROOM ATTENDANCE DATABASE ===")
        
        sec_10b = Section(name='10-B')
        sec_10c = Section(name='10-C')
        db.add_all([sec_10b, sec_10c])
        db.commit()
        db.refresh(sec_10b)
        db.refresh(sec_10c)
        print(f"[+] Created Sections: 10-B (id={sec_10b.id}), 10-C (id={sec_10c.id})")

        admin_user = User(
            email='admin@school.edu',
            hashed_password=hash_password('admin123'),
            full_name='System Admin',
            role=Role.admin
        )
        db.add(admin_user)

        teacher_physics = User(
            email='teacher.physics@school.edu',
            hashed_password=hash_password('teacher123'),
            full_name='Dr. Physics Teacher',
            role=Role.teacher
        )
        teacher_chem = User(
            email='teacher.chem@school.edu',
            hashed_password=hash_password('teacher123'),
            full_name='Prof. Chem Teacher',
            role=Role.teacher
        )
        db.add_all([teacher_physics, teacher_chem])
        db.commit()
        print("[+] Created Admin and Teacher accounts")

        student_data = [
            ('asha@school.edu', 'Asha Sharma'),
            ('bala@school.edu', 'Bala Kumar'),
            ('cira@school.edu', 'Cira Gupta'),
            ('dev@school.edu', 'Dev Patel'),
        ]
        
        seeded_students = []
        np.random.seed(42)

        for email, full_name in student_data:
            user = User(
                email=email,
                hashed_password=hash_password('student123'),
                full_name=full_name,
                role=Role.student
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            student = Student(user_id=user.id, section_id=sec_10b.id)
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
            db.commit()
            
            seeded_students.append((user, student, norm_vec))
            print(f"  - Enrolled student {full_name} ({email}) with synthetic 128-d face embedding")

        asha_embedding = seeded_students[0][2]
        with open(os.path.join(os.path.dirname(__file__), 'asha_synthetic_embedding.json'), 'w') as f:
            json.dump(asha_embedding, f)

        now = datetime.utcnow()
        day_of_week = now.weekday()

        # ROOM-101: started 5 min ago, 15-min grace -> should be within grace (on time)
        start_dt_101 = now - timedelta(minutes=5)
        end_dt_101 = now + timedelta(minutes=115)
        entry_101 = TimetableEntry(
            section_id=sec_10b.id,
            teacher_id=teacher_physics.id,
            subject='Physics',
            room='ROOM-101',
            day_of_week=day_of_week,
            start_time=time(start_dt_101.hour, start_dt_101.minute, start_dt_101.second),
            end_time=time(end_dt_101.hour, end_dt_101.minute, end_dt_101.second),
            late_grace_minutes=15,
            early_exit_buffer_minutes=10
        )
        db.add(entry_101)

        # ROOM-102: started 30 min ago, 15-min grace -> should be past grace (late)
        start_dt_102 = now - timedelta(minutes=30)
        end_dt_102 = now + timedelta(minutes=90)
        entry_102 = TimetableEntry(
            section_id=sec_10c.id,
            teacher_id=teacher_chem.id,
            subject='Chemistry',
            room='ROOM-102',
            day_of_week=day_of_week,
            start_time=time(start_dt_102.hour, start_dt_102.minute, start_dt_102.second),
            end_time=time(end_dt_102.hour, end_dt_102.minute, end_dt_102.second),
            late_grace_minutes=15,
            early_exit_buffer_minutes=10
        )
        db.add(entry_102)
        db.commit()
        db.refresh(entry_101)
        db.refresh(entry_102)
        active_entry = entry_101
        print(f"[+] Created Active Timetable Slot: ROOM-101, Section 10-B, Physics (Slot ID {entry_101.id}) - on time")
        print(f"[+] Created Active Timetable Slot: ROOM-102, Section 10-C, Chemistry (Slot ID {entry_102.id}) - late")

        asha_student = seeded_students[0][1]
        absence_count = 0
        for day in range(1, 25):
            try:
                rec_date = datetime(now.year, now.month, day, 10, 0, 0)
                if rec_date < now - timedelta(days=1) and absence_count < 9:
                    abs_rec = AttendanceRecord(
                        student_id=asha_student.id,
                        timetable_entry_id=active_entry.id,
                        date=rec_date,
                        status=AttendanceStatus.absent
                    )
                    db.add(abs_rec)
                    absence_count += 1
            except ValueError:
                pass
        
        db.commit()
        print(f"[+] Seeded {absence_count} historical absence records for Asha in current month ({now.strftime('%Y-%m')})")
        print("=== SEED COMPLETE ===")
        
    finally:
        db.close()

if __name__ == '__main__':
    seed_database()
