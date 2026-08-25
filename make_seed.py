"""
Seed script for Classroom Attendance hackathon database.
Populates sections, admin/teacher/student accounts, synthetic enrolled face embeddings,
active timetable entries centered around the current time, and historical absence records.
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
        
        # 2. Sections
        sec_10b = Section(name='10-B')
        sec_10c = Section(name='10-C')
        db.add_all([sec_10b, sec_10c])
        db.commit()
        db.refresh(sec_10b)
        db.refresh(sec_10c)
        print(f"[+] Created Sections: 10-B (id={sec_10b.id}), 10-C (id={sec_10c.id})")

        # 3. Admin user
        admin_user = User(
            email='admin@school.edu',
            hashed_password=hash_password('admin123'),
            full_name='System Admin',
            role=Role.admin
        )
        db.add(admin_user)

        # 4. Teachers
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

        # 5. Students in 10-B & 10-C
        student_data = [
            ('asha@school.edu', 'Asha Sharma', sec_10b.id),
            ('bala@school.edu', 'Bala Kumar', sec_10b.id),
            ('cira@school.edu', 'Cira Gupta', sec_10b.id),
            ('dev@school.edu', 'Dev Patel', sec_10b.id),
            ('ekta@school.edu', 'Ekta Verma', sec_10c.id),
        ]
        
        seeded_students = []
        np.random.seed(42)

        for email, full_name, sec_id in student_data:
            user = User(
                email=email,
                hashed_password=hash_password('student123'),
                full_name=full_name,
                role=Role.student
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            student = Student(user_id=user.id, section_id=sec_id)
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

        # 6. Timetable Entries (active right now)
        now = datetime.utcnow()
        day_of_week = now.weekday()  # 0=Monday ... 6=Sunday
        
        # Slot 1: ROOM-101 (Section 10-B, Physics) - On Time slot (5 mins ago, 15 min grace window)
        start_dt_1 = now - timedelta(minutes=5)
        end_dt_1 = now + timedelta(minutes=90)
        
        active_entry_1 = TimetableEntry(
            section_id=sec_10b.id,
            teacher_id=teacher_physics.id,
            subject='Physics',
            room='ROOM-101',
            day_of_week=day_of_week,
            start_time=time(start_dt_1.hour, start_dt_1.minute, start_dt_1.second),
            end_time=time(end_dt_1.hour, end_dt_1.minute, end_dt_1.second),
            late_grace_minutes=15,
            early_exit_buffer_minutes=10
        )
        
        # Slot 2: ROOM-102 (Section 10-C, Chemistry) - Late slot (30 mins ago, 15 min grace window)
        start_dt_2 = now - timedelta(minutes=30)
        end_dt_2 = now + timedelta(minutes=90)
        
        active_entry_2 = TimetableEntry(
            section_id=sec_10c.id,
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
        print(f"[+] Created Active On-Time Timetable Slot: ROOM-101, Section 10-B, Physics (ID {active_entry_1.id})")
        print(f"[+] Created Active Late Timetable Slot: ROOM-102, Section 10-C, Chemistry (ID {active_entry_2.id})")

        # 7. Historical Absences for Asha (9 records)
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
        print("=== SEED COMPLETE ===")
        
    finally:
        db.close()

if __name__ == '__main__':
    seed_database()
