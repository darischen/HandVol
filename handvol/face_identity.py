"""dlib-based face identity embeddings.

`compute_identity_embedding` is a synchronous helper used by the
calibration flow (where latency does not matter — the user is paused
for a countdown anyway).

`IdentityEncoder` (added in a separate task) is the runtime async
worker that throttles dlib calls to ~3 Hz on a background thread.
"""
from __future__ import annotations

import logging
import threading
import time as _time

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


class IdentityEncoder:
    """Async, coalescing-rate-limited dlib face encoder.

    Owns a single background thread. `submit(rgb, bbox)` is
    fire-and-forget: it returns immediately and drops the submission if
    a previous job is still running OR if wall-clock time since the
    last submitted job is less than `min_interval_ms`. `latest()`
    returns the most recent successful embedding, never blocks.

    `encoding_fn` is injected for testability — production callers use
    the module default (`compute_identity_embedding`).
    """

    def __init__(self, encoding_fn=None, min_interval_ms=MIN_INTERVAL_MS):
        self._encoding_fn = encoding_fn or compute_identity_embedding
        self._min_interval_s = min_interval_ms / 1000.0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._next_job = None  # (rgb, bbox) or None
        self._in_flight = False
        self._last_submit_t = 0.0
        self._latest_embedding = None
        self._latest_ts_ns = 0
        self._thread = None
        self._warned_no_face = False  # rate-limit the "dlib found no face" log

    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def submit(self, rgb, bbox):
        now = _time.monotonic()
        with self._lock:
            if self._in_flight:
                return
            if now - self._last_submit_t < self._min_interval_s:
                return
            self._next_job = (rgb, bbox)
            self._in_flight = True
            self._last_submit_t = now
        self._wake.set()

    def latest(self):
        with self._lock:
            return self._latest_embedding, self._latest_ts_ns

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                job = self._next_job
                self._next_job = None
            if job is None:
                with self._lock:
                    self._in_flight = False
                continue
            rgb, bbox = job
            raised = False
            try:
                emb = self._encoding_fn(rgb, bbox)
            except Exception:
                _log.exception("IdentityEncoder: encoding_fn raised")
                emb = None
                raised = True
            if emb is not None:
                with self._lock:
                    self._latest_embedding = emb
                    self._latest_ts_ns = _time.monotonic_ns()
                    self._warned_no_face = False  # reset on success
            elif not raised and not self._warned_no_face:
                _log.warning(
                    "IdentityEncoder: encoding_fn returned no embedding "
                    "(dlib could not find a face in the given crop). "
                    "Suppressing further warnings until a successful encode."
                )
                self._warned_no_face = True
            with self._lock:
                self._in_flight = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
