"""
Face detection + recognition, scoped to a single class roster (not the
whole school) — smaller candidate pool = faster and more accurate matches,
per the spec's checkpoint design.

Uses face_recognition (dlib-based) by default. If dlib setup becomes a
pain (common on Windows — needs CMake + a C++ toolchain), swap the
`_get_face_embedding` implementation for MediaPipe Face Mesh + a
lightweight embedding model instead; the rest of this module's interface
stays the same.
"""

import json
from dataclasses import dataclass
from typing import Optional

import face_recognition
import numpy as np
from sqlalchemy.orm import Session

from models import Student, EnrolledFace

# Lower = stricter match. face_recognition's default distance metric is
# Euclidean distance between 128-d embeddings; 0.6 is the library's own
# recommended default. Tune this conservatively during rehearsal —
# false rejections are more embarrassing live than false acceptances
# (see spec section 6).
MATCH_THRESHOLD = 0.55


@dataclass
class RecognitionResult:
    matched: bool
    student_id: Optional[int]
    confidence: Optional[float]  # 0-1, higher = better match


def _extract_embedding(frame: np.ndarray) -> Optional[np.ndarray]:
    """Detect the largest/most prominent face in a frame and return its
    128-d embedding, or None if no face is found."""
    face_locations = face_recognition.face_locations(frame)
    if not face_locations:
        return None
    encodings = face_recognition.face_encodings(frame, known_face_locations=face_locations)
    return encodings[0] if encodings else None


def get_best_embedding_from_burst(frames: list[np.ndarray]) -> Optional[np.ndarray]:
    """A checkpoint scan sends a burst of frames (needed for liveness
    anyway — see liveness.py). Try each frame until a face is found;
    in practice the first clear, front-facing frame in the burst wins."""
    for frame in frames:
        embedding = _extract_embedding(frame)
        if embedding is not None:
            return embedding
    return None


def recognize_against_roster(
    db: Session, embedding: np.ndarray, section_id: int
) -> RecognitionResult:
    """Match `embedding` only against students enrolled in `section_id` —
    the roster the timetable engine resolved as active for this room/time.
    """
    roster_faces = (
        db.query(EnrolledFace)
        .join(Student, Student.id == EnrolledFace.student_id)
        .filter(Student.section_id == section_id)
        .all()
    )

    if not roster_faces:
        return RecognitionResult(matched=False, student_id=None, confidence=None)

    known_embeddings = [np.array(json.loads(f.embedding)) for f in roster_faces]
    distances = face_recognition.face_distance(known_embeddings, embedding)

    best_idx = int(np.argmin(distances))
    best_distance = float(distances[best_idx])

    if best_distance > MATCH_THRESHOLD:
        return RecognitionResult(matched=False, student_id=None, confidence=None)

    confidence = max(0.0, 1.0 - best_distance)  # rough 0-1 confidence for the API response
    return RecognitionResult(
        matched=True,
        student_id=roster_faces[best_idx].student_id,
        confidence=round(confidence, 3),
    )
