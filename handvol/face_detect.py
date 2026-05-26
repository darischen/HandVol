"""MediaPipe Face Landmarker wrapper + landmark-to-embedding helper.

The embedder runs in LIVE_STREAM mode, mirroring the gesture recognizer
pattern in capture.py. The embedding helper is intentionally a pure
function so it can be unit-tested without the model or a camera.
"""
from pathlib import Path

import numpy as np


EXPECTED_LANDMARK_COUNT = 478  # MediaPipe Face Landmarker output
FACE_MODEL_FILENAME = "face_landmarker.task"


def landmarks_to_embedding(landmarks):
    """Convert face landmarks to a translation+scale-invariant identity vector.

    Steps:
      1. Stack the (x, y, z) of each NormalizedLandmark into an (N, 3) array.
      2. Subtract the centroid so the embedding is invariant to where the
         face is located in the frame.
      3. Divide by the RMS distance from the centroid so it is invariant to
         how close the face is to the camera.
      4. Flatten to a 1-D vector; cosine similarity on this vector compares
         relative facial geometry, which is the part that is identity-bearing.

    Returns None if the input is missing or has fewer landmarks than the
    Face Landmarker is expected to emit.
    """
    if not landmarks or len(landmarks) < EXPECTED_LANDMARK_COUNT:
        return None
    pts = np.asarray(
        [(lm.x, lm.y, lm.z) for lm in landmarks[:EXPECTED_LANDMARK_COUNT]],
        dtype=np.float32,
    )
    pts -= pts.mean(axis=0, keepdims=True)
    scale = float(np.sqrt((pts ** 2).sum() / pts.shape[0]))
    if scale < 1e-9:
        return None
    pts /= scale
    return pts.reshape(-1)
