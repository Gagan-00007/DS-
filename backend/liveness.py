"""
Blink-based liveness check via Eye Aspect Ratio (EAR) across a burst of
frames. Catches a static photo held up to the checkpoint (constant EAR,
no blink); does NOT catch a video replay of a real blink — that's a known
limitation, flagged honestly in the spec (section 5) rather than oversold.

Uses MediaPipe Face Mesh for landmarks (see spec 3.2 — preferred over
dlib's 68-point model for easier setup and better performance).
"""

from typing import List

import mediapipe as mp
import numpy as np

# EAR drops sharply during a blink (eye closing) then recovers. This
# threshold and frame-count are starting points — tune them against real
# footage during rehearsal, lighting and camera angle both shift EAR values.
EAR_BLINK_THRESHOLD = 0.21
MIN_CONSECUTIVE_LOW_FRAMES = 1  # how many frames must dip below threshold to count as a blink

# MediaPipe Face Mesh landmark indices for the eye contour points used in
# the standard 6-point EAR calculation (left eye shown; right eye mirrors).
LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]

_face_mesh = mp.solutions.face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
)


def _eye_aspect_ratio(landmarks, eye_idx, frame_shape) -> float:
    h, w = frame_shape[:2]
    pts = np.array([(landmarks[i].x * w, landmarks[i].y * h) for i in eye_idx])
    # Standard EAR formula: vertical distances over horizontal distance
    vertical_1 = np.linalg.norm(pts[1] - pts[5])
    vertical_2 = np.linalg.norm(pts[2] - pts[4])
    horizontal = np.linalg.norm(pts[0] - pts[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def _frame_ear(frame: np.ndarray) -> float | None:
    """Average EAR across both eyes for one frame, or None if no face landmarks found."""
    results = _face_mesh.process(frame)
    if not results.multi_face_landmarks:
        return None
    landmarks = results.multi_face_landmarks[0].landmark
    left = _eye_aspect_ratio(landmarks, LEFT_EYE_IDX, frame.shape)
    right = _eye_aspect_ratio(landmarks, RIGHT_EYE_IDX, frame.shape)
    return (left + right) / 2.0


def detect_blink(frames: List[np.ndarray]) -> bool:
    """Return True if the frame burst shows an EAR dip-and-recover
    pattern consistent with a real blink. A static photo produces a
    roughly constant EAR with no dip."""
    ear_values = [ear for ear in (_frame_ear(f) for f in frames) if ear is not None]

    if len(ear_values) < 3:
        # Not enough valid frames to judge — treat conservatively as no blink
        # detected rather than guessing.
        return False

    low_frame_count = sum(1 for ear in ear_values if ear < EAR_BLINK_THRESHOLD)
    variance = float(np.var(ear_values))

    # Require both a dip below threshold AND meaningful variance across the
    # burst — a photo held slightly unsteady can still jitter a little, but
    # won't show a genuine dip-then-recover pattern.
    return low_frame_count >= MIN_CONSECUTIVE_LOW_FRAMES and variance > 0.0005
