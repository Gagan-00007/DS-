"""
Run this once per student, offline, before the event — NOT part of the
live demo flow. Takes 2-3 reference photos, computes a face embedding,
and links it to a Student record + Department roster.

Usage:
    python enroll.py --email student@example.com --name "Asha Rao" \
        --department "Computer Science" --photos photo1.jpg photo2.jpg photo3.jpg

Prerequisite: the Department must already exist (create departments + teachers
via a small seed script before running enrollment).
"""

import argparse
import json

import cv2
import numpy as np

from database import SessionLocal, init_db
from models import User, Student, Department, EnrolledFace, Role
from auth import hash_password
import recognition


def load_frame(path: str) -> np.ndarray:
    frame = cv2.imread(path)
    if frame is None:
        raise ValueError(f"Could not read image: {path}")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def enroll_student(email: str, full_name: str, department_name: str, photo_paths: list[str],
                    temp_password: str = "changeme123"):
    init_db()
    db = SessionLocal()
    try:
        department = db.query(Department).filter(Department.name == department_name).first()
        if department is None:
            raise ValueError(
                f"Department '{department_name}' does not exist — create it first via a seed script."
            )

        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValueError(f"User with email {email} already exists.")

        # Compute an embedding from the first photo that yields a clear face.
        embedding = None
        for path in photo_paths:
            frame = load_frame(path)
            embedding = recognition._extract_embedding(frame)
            if embedding is not None:
                break
        if embedding is None:
            raise ValueError(
                f"No face detected in any of the provided photos for {full_name}. "
                "Retake with better lighting/framing."
            )

        user = User(
            email=email, full_name=full_name, role=Role.student,
            hashed_password=hash_password(temp_password),
        )
        db.add(user)
        db.flush()

        student = Student(user_id=user.id, department_id=department.id)
        db.add(student)
        db.flush()

        face = EnrolledFace(student_id=student.id, embedding=json.dumps(embedding.tolist()))
        db.add(face)

        db.commit()
        print(f"Enrolled {full_name} ({email}) in department {department_name}. "
              f"Temporary password: {temp_password}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enroll a student's face + account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--department", required=True)
    parser.add_argument("--photos", nargs="+", required=True)
    args = parser.parse_args()

    enroll_student(args.email, args.name, args.department, args.photos)
