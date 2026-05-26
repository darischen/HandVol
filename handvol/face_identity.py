"""dlib-based face identity embeddings.

`compute_identity_embedding` is a synchronous helper used by the
calibration flow (where latency does not matter — the user is paused
for a countdown anyway).

`IdentityEncoder` (added in a separate task) is the runtime async
worker that throttles dlib calls to ~3 Hz on a background thread.
"""
from __future__ import annotations

import logging

import face_recognition
import numpy as np


MIN_INTERVAL_MS = 333  # ~3 Hz cap on runtime dlib calls
JITTERS = 1            # face_recognition default; higher = slower, more stable
EMBEDDING_DIM = 128    # dlib ResNet-34 output dimension


_log = logging.getLogger(__name__)


def compute_identity_embedding(rgb_frame, bbox):
    """Compute a single 128-D L2-normalized identity embedding.

    Args:
      rgb_frame: HxWx3 numpy array, RGB order, uint8.
      bbox: (top, right, bottom, left) in pixels, as returned by
        `face_detect.landmarks_to_bbox`. Passed to face_recognition via
        `known_face_locations` so dlib skips its HOG detector.

    Returns:
      np.ndarray of shape (128,) float32, L2-normalized, or None if
      dlib found no face in the provided crop.
    """
    if bbox is None:
        return None
    encodings = face_recognition.face_encodings(
        rgb_frame,
        known_face_locations=[bbox],
        num_jitters=JITTERS,
    )
    if not encodings:
        return None
    emb = np.asarray(encodings[0], dtype=np.float32)
    norm = float(np.linalg.norm(emb))
    if norm < 1e-9:
        return None
    return emb / norm
