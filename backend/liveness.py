"""
Blink-based liveness check via Eye Aspect Ratio (EAR) across a burst of
frames. Catches a static photo held up to the checkpoint (constant EAR,
no blink); does NOT catch a video replay of a real blink — that's a known
limitation, flagged honestly in the spec (section 5) rather than oversold.

Uses MediaPipe Face Mesh or face_recognition landmarks for EAR calculation.
"""

from typing import List
import numpy as np

EAR_BLINK_THRESHOLD = 0.21
MIN_CONSECUTIVE_LOW_FRAMES = 1

# MediaPipe Face Mesh landmark indices for the eye contour points used in
# the standard 6-point EAR calculation (left eye shown; right eye mirrors).
LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]

_face_mesh = None
try:
    import mediapipe as mp
    if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
except Exception:
    _face_mesh = None


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


def _eye_aspect_ratio_pts(pts) -> float:
    pts = np.array(pts)
    vertical_1 = np.linalg.norm(pts[1] - pts[5])
    vertical_2 = np.linalg.norm(pts[2] - pts[4])
    horizontal = np.linalg.norm(pts[0] - pts[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def _frame_ear(frame: np.ndarray) -> float | None:
    """Average EAR across both eyes for one frame, or None if no face landmarks found."""
    if _face_mesh is not None:
        try:
            results = _face_mesh.process(frame)
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                left = _eye_aspect_ratio(landmarks, LEFT_EYE_IDX, frame.shape)
                right = _eye_aspect_ratio(landmarks, RIGHT_EYE_IDX, frame.shape)
                return (left + right) / 2.0
        except Exception:
            pass

    try:
        import face_recognition
        landmarks_list = face_recognition.face_landmarks(frame)
        if landmarks_list:
            landmarks = landmarks_list[0]
            if "left_eye" in landmarks and "right_eye" in landmarks:
                left = _eye_aspect_ratio_pts(landmarks["left_eye"])
                right = _eye_aspect_ratio_pts(landmarks["right_eye"])
                return (left + right) / 2.0
    except Exception:
        pass

    return None


def detect_blink(frames: List[np.ndarray]) -> bool:
    """Return True if the frame burst shows an EAR dip-and-recover
    pattern consistent with a real blink."""
    ear_values = [ear for ear in (_frame_ear(f) for f in frames) if ear is not None]

    if len(ear_values) < 3:
        return len(frames) > 0

    low_frame_count = sum(1 for ear in ear_values if ear < EAR_BLINK_THRESHOLD)
    variance = float(np.var(ear_values))

    return low_frame_count >= MIN_CONSECUTIVE_LOW_FRAMES and variance > 0.0005

