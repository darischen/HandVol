# dlib Face Identity Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the MediaPipe-landmark identity embedding with dlib's `face_recognition` (128-D ResNet) on a throttled async worker, while keeping MediaPipe Face Landmarker as the per-frame face *detector* and overlay producer.

**Architecture:** A new `handvol/face_identity.py` module owns dlib. It exposes a synchronous `compute_identity_embedding(rgb, bbox)` for calibration and an `IdentityEncoder` async worker (coalescing rate-limiter at ~3 Hz) for the runtime loop. MediaPipe stays in `capture.py` for fast per-frame face detection + bbox + dots; we feed its bbox to dlib via `known_face_locations` to skip dlib's slow HOG detector. `FaceProfile` is unchanged structurally — only `PROFILE_VERSION` bumps `1 → 2` so existing v1 files are rejected at load.

**Tech Stack:** `face_recognition` (dlib ResNet-34), `numpy`, MediaPipe Tasks (FaceLandmarker, GestureRecognizer), OpenCV, pystray, existing handvol modules.

**Spec:** `docs/superpowers/specs/2026-05-26-dlib-face-identity-design.md`

---

## File Structure

**Create:**
- `handvol/face_identity.py` — `compute_identity_embedding()` sync helper + `IdentityEncoder` async worker.
- `tests/test_face_identity.py` — five rate-limiter tests for `IdentityEncoder`, all using a mocked encoding function (no dlib invocation).

**Modify:**
- `requirements.txt` — add `face_recognition` (and `dlib` is its transitive dep, but call it out for clarity since the user installs it from a prebuilt wheel).
- `README.md` — add a short "Install dlib" note pointing at a prebuilt wheel since pip-from-source needs CMake + VS Build Tools.
- `handvol/face_profile.py` — bump `PROFILE_VERSION = 2`; in `load()`, reject any file whose stored `version != PROFILE_VERSION`. `MATCH_THRESHOLD` stays at `0.92` (re-tune in Task 9).
- `handvol/face_detect.py` — **remove** `landmarks_to_embedding`, `EXPECTED_LANDMARK_COUNT`; **add** `landmarks_to_bbox(face_landmarks, frame_shape) -> (top, right, bottom, left)`. `FaceEmbedder` (the MediaPipe wrapper) and `landmarks_to_bbox` are the only things that file is now responsible for.
- `handvol/capture.py` — `GestureSource` constructs an `IdentityEncoder` alongside its existing `FaceEmbedder`. On each frame, pick the **largest** MediaPipe-detected face by bbox area and submit `(rgb, bbox)` to the identity encoder. Result tuple changes from `(gesture, score, landmarks, face_embs, face_lms)` to `(gesture, score, landmarks, face_lms, identity_emb)`.
- `handvol/calibration.py` — replace `embedder.latest()` per-pose call with a synchronous `compute_identity_embedding(rgb, bbox)` call.
- `handvol.pyw` — add `face_recognition` import-availability check at startup; update result-tuple unpacking; switch matching from `any(profile.matches(e)[0] for e in face_embs)` to a single `profile.matches(identity_emb)`. Drop the `face_embs` variable entirely.

**Delete:**
- `tests/test_face_embedding.py` — tests a function (`landmarks_to_embedding`) that no longer exists.

**Constants (all module-level, near the top of their owning file):**
- `face_identity.py`: `MIN_INTERVAL_MS = 333`, `JITTERS = 1`, `EMBEDDING_DIM = 128`.
- `face_profile.py`: `PROFILE_VERSION = 2`, `MATCH_THRESHOLD = 0.92` (unchanged numerically, but a fresh tuning target).

---

## Task 1: Update dependencies and README install note

**Files:**
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] **Step 1: Add `face_recognition` to `requirements.txt`**

Open `requirements.txt`. Append at the end:

```
face_recognition>=1.3.0
```

(Note: `face_recognition` declares `dlib` as a dependency. dlib itself is installed separately from a prebuilt wheel because compiling it from source on Windows requires CMake + VS Build Tools. The README will document this.)

- [ ] **Step 2: Update README install instructions**

Find the existing **Setup** section in `README.md`. After the existing block:

```powershell
# from the repo root
pip install -r requirements.txt
```

Add a new subsection (before "Download the MediaPipe gesture model bundle"):

````markdown
### Installing dlib on Windows

`face_recognition` depends on `dlib`, which has no official Windows
wheel on PyPI. Install a community-built wheel for your Python version
**before** running `pip install -r requirements.txt`:

1. Download a matching wheel from https://github.com/z-mahmud22/Dlib_Windows_Python3.x/releases (or any trusted source).
2. `pip install path\to\dlib-19.xx.x-cpxx-cpxx-win_amd64.whl`
3. Then run `pip install -r requirements.txt`.

dlib runs on CPU only via this wheel. Face encoding takes ~30-80 ms per
call; the runtime loop throttles it to ~3 Hz so the main FPS is
unaffected.
````

- [ ] **Step 3: Verify**

```bash
git status
```
Expected: `requirements.txt` and `README.md` show as modified.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt README.md
git commit -m "chore(face): document dlib install + add face_recognition dependency"
```

---

## Task 2: Bump `PROFILE_VERSION` and reject v1 profiles

**Files:**
- Modify: `handvol/face_profile.py`
- Modify: `tests/test_face_profile.py`

- [ ] **Step 1: Write a failing test for v1 rejection**

Open `tests/test_face_profile.py`. Append at the bottom:

```python
def test_load_rejects_v1_profile(tmp_path):
    # Write a profile with the OLD version=1 marker; load() must reject it.
    import numpy as np
    path = tmp_path / "v1.npz"
    np.savez(
        path,
        embeddings=np.zeros((3, 1434), dtype=np.float32),
        created_at=np.array("2026-01-01"),
        version=np.array(1),
    )
    assert FaceProfile.load(path) is None
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
python -m pytest tests/test_face_profile.py::test_load_rejects_v1_profile -v
```
Expected: FAIL — current code loads v1 fine (the existing logic only checks `embeddings.ndim`, not the version number).

- [ ] **Step 3: Bump the version and reject mismatched versions in `load`**

In `handvol/face_profile.py`:

Find the line:
```python
PROFILE_VERSION = 1
```

Change it to:
```python
PROFILE_VERSION = 2
```

Find the `load` classmethod. After this block:

```python
        try:
            with np.load(path, allow_pickle=False) as data:
                embeddings = data["embeddings"]
                created_at = str(data["created_at"]) if "created_at" in data else ""
                version = int(data["version"]) if "version" in data else PROFILE_VERSION
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile) as exc:
            _log.warning("Failed to load face profile at %s: %s", path, exc)
            return None
```

Add (immediately AFTER the `try/except` block, BEFORE the existing `if embeddings.ndim != 2:` check):

```python
        if version != PROFILE_VERSION:
            _log.warning(
                "face profile at %s is version %d; this build expects version %d "
                "— please re-calibrate.",
                path, version, PROFILE_VERSION,
            )
            return None
```

- [ ] **Step 4: Run the new test — confirm it passes**

```bash
python -m pytest tests/test_face_profile.py::test_load_rejects_v1_profile -v
```
Expected: PASS.

- [ ] **Step 5: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all tests pass (the existing 9 face_profile tests use `FaceProfile.create_empty(...).save(...)` which writes the current `PROFILE_VERSION = 2`, so they round-trip cleanly).

- [ ] **Step 6: Commit**

```bash
git add handvol/face_profile.py tests/test_face_profile.py
git commit -m "feat(face): bump PROFILE_VERSION to 2; reject v1 profiles at load"
```

---

## Task 3: Replace `landmarks_to_embedding` with `landmarks_to_bbox`

**Files:**
- Modify: `handvol/face_detect.py`
- Delete: `tests/test_face_embedding.py`

The MediaPipe-landmark identity helper is being retired. In its place we need a small helper that converts MediaPipe's normalized landmark coordinates into the pixel `(top, right, bottom, left)` tuple that `face_recognition`'s `known_face_locations=` parameter expects.

- [ ] **Step 1: Read the current `handvol/face_detect.py`**

Use the Read tool. Note the current structure: module docstring, imports (`threading`, `time`, `Path`, `mediapipe`, `numpy`, mp tasks), constants (`EXPECTED_LANDMARK_COUNT`, `FACE_MODEL_FILENAME`, `_DEFAULT_MODEL_PATH`, `MAX_FACES`), the `landmarks_to_embedding` function, and the `FaceEmbedder` class.

- [ ] **Step 2: Remove the dead helper and constant**

Delete these from `handvol/face_detect.py`:
- The `EXPECTED_LANDMARK_COUNT = 478` constant line.
- The entire `landmarks_to_embedding` function (defined just above the `FaceEmbedder` class).
- The unused `import numpy as np` line ONLY IF no other code in the file uses `np` after the function is removed. (`FaceEmbedder` does not use numpy directly — verify with a quick search before removing the import.)

Then **update** `FaceEmbedder._on_result`. The current callback calls `landmarks_to_embedding(face)`. Since that function is gone, change the callback to store the raw landmark lists only:

Replace this method body:

```python
    def _on_result(self, result, output_image, timestamp_ms):
        embeddings: list = []
        face_landmarks_list: list = []
        if result.face_landmarks:
            for face in result.face_landmarks:
                emb = landmarks_to_embedding(face)
                if emb is not None:
                    embeddings.append(emb)
                    face_landmarks_list.append(face)
        with self._lock:
            self._latest_embeddings = embeddings
            self._latest_face_landmarks = face_landmarks_list
            self._latest_ts_ns = time.monotonic_ns()
```

With:

```python
    def _on_result(self, result, output_image, timestamp_ms):
        face_landmarks_list: list = []
        if result.face_landmarks:
            face_landmarks_list = list(result.face_landmarks)
        with self._lock:
            self._latest_face_landmarks = face_landmarks_list
            self._latest_ts_ns = time.monotonic_ns()
```

Replace the `__init__` body:

```python
    def __init__(self, model_path=None):
        self.model_path = str(model_path or _DEFAULT_MODEL_PATH)
        self._lock = threading.Lock()
        self._latest_embeddings: list = []  # list[np.ndarray]
        self._latest_face_landmarks: list = []  # list[list[NormalizedLandmark]]
        self._latest_ts_ns = 0
        self._landmarker = None
```

With:

```python
    def __init__(self, model_path=None):
        self.model_path = str(model_path or _DEFAULT_MODEL_PATH)
        self._lock = threading.Lock()
        self._latest_face_landmarks: list = []  # list[list[NormalizedLandmark]]
        self._latest_ts_ns = 0
        self._landmarker = None
```

Replace the `latest()` method:

```python
    def latest(self):
        """Return (embeddings_list, face_landmarks_list, ts_ns).

        embeddings_list and face_landmarks_list are aligned: index i in
        each refers to the same detected face. Both are empty when no
        face was detected in the most recent frame.
        """
        with self._lock:
            return (
                list(self._latest_embeddings),
                list(self._latest_face_landmarks),
                self._latest_ts_ns,
            )
```

With:

```python
    def latest(self):
        """Return (face_landmarks_list, ts_ns).

        face_landmarks_list is a list of lists of NormalizedLandmark, one
        inner list per detected face. Empty when no face was detected in
        the most recent frame.
        """
        with self._lock:
            return list(self._latest_face_landmarks), self._latest_ts_ns
```

- [ ] **Step 3: Add `landmarks_to_bbox` helper**

Add this function to `handvol/face_detect.py`, immediately ABOVE the `FaceEmbedder` class:

```python
def landmarks_to_bbox(face_landmarks, frame_shape):
    """Compute the pixel bbox enclosing a MediaPipe face landmark list.

    `face_landmarks` is a list of NormalizedLandmark objects (478 entries
    from the Face Landmarker). `frame_shape` is `(h, w)` or `(h, w, c)`.

    Returns `(top, right, bottom, left)` in pixel coords — the format
    `face_recognition.face_encodings`' `known_face_locations` parameter
    expects. Returns None for empty input.
    """
    if not face_landmarks:
        return None
    h = frame_shape[0]
    w = frame_shape[1]
    xs = [lm.x for lm in face_landmarks]
    ys = [lm.y for lm in face_landmarks]
    left = max(0, int(min(xs) * w))
    right = min(w, int(max(xs) * w))
    top = max(0, int(min(ys) * h))
    bottom = min(h, int(max(ys) * h))
    return (top, right, bottom, left)
```

- [ ] **Step 4: Delete the obsolete test file**

```bash
rm tests/test_face_embedding.py
```

- [ ] **Step 5: Smoke-test imports**

```bash
python -c "from handvol.face_detect import FaceEmbedder, landmarks_to_bbox, MAX_FACES; print('ok', MAX_FACES)"
```
Expected: `ok 3`.

- [ ] **Step 6: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: 17 tests pass (was 22; we removed 5 from `test_face_embedding.py`).

- [ ] **Step 7: Commit**

```bash
git add handvol/face_detect.py
git rm tests/test_face_embedding.py
git commit -m "refactor(face): drop landmark embedding; add landmarks_to_bbox helper"
```

---

## Task 4: Synchronous `compute_identity_embedding` in new `face_identity.py`

**Files:**
- Create: `handvol/face_identity.py`

This task adds only the synchronous helper. The async `IdentityEncoder` is added in Task 5.

- [ ] **Step 1: Create `handvol/face_identity.py`**

Write the file:

```python
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
```

- [ ] **Step 2: Smoke-test the import (does NOT run dlib)**

```bash
python -c "from handvol.face_identity import compute_identity_embedding, MIN_INTERVAL_MS, EMBEDDING_DIM; print('ok', MIN_INTERVAL_MS, EMBEDDING_DIM)"
```
Expected: `ok 333 128`.

(If this fails with `ImportError: No module named 'face_recognition'`, dlib install needs to be fixed before continuing — see Task 1's README note.)

- [ ] **Step 3: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: 17 tests pass.

- [ ] **Step 4: Commit**

```bash
git add handvol/face_identity.py
git commit -m "feat(face): compute_identity_embedding sync helper via face_recognition"
```

---

## Task 5: `IdentityEncoder` async worker with coalescing rate-limiter

**Files:**
- Modify: `handvol/face_identity.py`
- Create: `tests/test_face_identity.py`

This task adds the runtime async worker. Tests use a mocked encoding function so dlib is never invoked.

- [ ] **Step 1: Write failing tests**

Create `tests/test_face_identity.py`:

```python
import time

import numpy as np
import pytest

from handvol.face_identity import IdentityEncoder, EMBEDDING_DIM


def _fake_emb(value=1.0):
    v = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    v[0] = value
    return v / np.linalg.norm(v)


def test_submit_drops_when_in_flight():
    """A submit while the previous job is still running is dropped."""
    running = []  # records calls
    proceed = [False]

    def slow_encode(rgb, bbox):
        running.append(("started", time.monotonic()))
        while not proceed[0]:
            time.sleep(0.01)
        running.append(("finished", time.monotonic()))
        return _fake_emb(1.0)

    enc = IdentityEncoder(encoding_fn=slow_encode, min_interval_ms=0)
    enc.start()
    try:
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))
        # Wait until the worker has actually started the slow job.
        for _ in range(100):
            if running:
                break
            time.sleep(0.01)
        # Now submit again — must be dropped because in-flight.
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))
        proceed[0] = True
        time.sleep(0.1)
    finally:
        enc.stop()

    # Only ONE encoding ran.
    started = [r for r in running if r[0] == "started"]
    assert len(started) == 1


def test_submit_drops_when_within_min_interval():
    """Two submits within MIN_INTERVAL_MS — the second is dropped."""
    calls = []

    def quick_encode(rgb, bbox):
        calls.append(time.monotonic())
        return _fake_emb(1.0)

    enc = IdentityEncoder(encoding_fn=quick_encode, min_interval_ms=300)
    enc.start()
    try:
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))
        time.sleep(0.05)  # let the first complete
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))  # within 300 ms — drop
        time.sleep(0.1)
    finally:
        enc.stop()

    assert len(calls) == 1


def test_submit_accepted_after_interval():
    """After MIN_INTERVAL_MS has passed, a second submit runs."""
    calls = []

    def quick_encode(rgb, bbox):
        calls.append(time.monotonic())
        return _fake_emb(value=len(calls) + 1.0)

    enc = IdentityEncoder(encoding_fn=quick_encode, min_interval_ms=100)
    enc.start()
    try:
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))
        time.sleep(0.2)  # > 100 ms
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))
        time.sleep(0.1)
    finally:
        enc.stop()

    assert len(calls) == 2


def test_latest_returns_most_recent_embedding():
    """latest() returns the embedding from the last completed job."""

    def quick_encode(rgb, bbox):
        return _fake_emb(value=2.5)

    enc = IdentityEncoder(encoding_fn=quick_encode, min_interval_ms=0)
    enc.start()
    try:
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))
        # Poll for completion.
        deadline = time.monotonic() + 1.0
        emb = None
        while time.monotonic() < deadline:
            emb, _ = enc.latest()
            if emb is not None:
                break
            time.sleep(0.01)
    finally:
        enc.stop()

    assert emb is not None
    expected = _fake_emb(value=2.5)
    np.testing.assert_allclose(emb, expected, rtol=1e-6)


def test_worker_exception_does_not_kill_thread():
    """If encoding_fn raises, the worker keeps accepting future jobs."""
    state = {"raise_once": True, "calls": 0}

    def flaky_encode(rgb, bbox):
        state["calls"] += 1
        if state["raise_once"]:
            state["raise_once"] = False
            raise RuntimeError("boom")
        return _fake_emb(value=3.5)

    enc = IdentityEncoder(encoding_fn=flaky_encode, min_interval_ms=0)
    enc.start()
    try:
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))  # raises
        time.sleep(0.1)
        enc.submit(rgb=None, bbox=(0, 1, 1, 0))  # should still run
        # Poll for completion of the second call.
        deadline = time.monotonic() + 1.0
        emb = None
        while time.monotonic() < deadline:
            emb, _ = enc.latest()
            if emb is not None:
                break
            time.sleep(0.01)
    finally:
        enc.stop()

    assert state["calls"] == 2
    assert emb is not None
```

- [ ] **Step 2: Run the tests — confirm they fail**

```bash
python -m pytest tests/test_face_identity.py -v
```
Expected: 5 FAILures with ImportError (`IdentityEncoder` does not exist yet).

- [ ] **Step 3: Implement `IdentityEncoder`**

Append to `handvol/face_identity.py`:

```python
import threading
import time as _time


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
            try:
                emb = self._encoding_fn(rgb, bbox)
            except Exception:
                _log.exception("IdentityEncoder: encoding_fn raised")
                emb = None
            if emb is not None:
                with self._lock:
                    self._latest_embedding = emb
                    self._latest_ts_ns = _time.monotonic_ns()
            with self._lock:
                self._in_flight = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
```

- [ ] **Step 4: Run the tests — confirm they pass**

```bash
python -m pytest tests/test_face_identity.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: 23 tests pass (10 face_profile + 8 scrubber + 5 face_identity).

- [ ] **Step 6: Commit**

```bash
git add handvol/face_identity.py tests/test_face_identity.py
git commit -m "feat(face): IdentityEncoder async worker with coalescing rate-limiter"
```

---

## Task 6: Wire `IdentityEncoder` into `GestureSource`

**Files:**
- Modify: `handvol/capture.py`

The capture layer now drives the dlib encoder on every frame (which the encoder will silently rate-limit). Result tuple changes from
`(gesture, score, hand_landmarks, face_embs, face_lms)` to
`(gesture, score, hand_landmarks, face_lms, identity_emb)`.

- [ ] **Step 1: Read `handvol/capture.py`**

Use the Read tool. Find the import block, `GestureSource.__init__`, `GestureSource.open`, `GestureSource.read`, `GestureSource.close`.

- [ ] **Step 2: Update imports**

In `handvol/capture.py`, replace:

```python
from handvol.face_detect import FaceEmbedder
```

With:

```python
from handvol.face_detect import FaceEmbedder, landmarks_to_bbox
from handvol.face_identity import IdentityEncoder
```

- [ ] **Step 3: Add `IdentityEncoder` to `__init__`**

In `GestureSource.__init__`, find:

```python
        self._embedder = FaceEmbedder()
```

After it, add:

```python
        self._identity = IdentityEncoder()
```

- [ ] **Step 4: Start/stop the identity encoder alongside the others**

In `GestureSource.open`, find the line `self._embedder.open()` (inside the try block). After it, add:

```python
            self._identity.start()
```

In `GestureSource.close`, find the line `self._embedder.close()`. Before it, add:

```python
        self._identity.stop()
```

- [ ] **Step 5: Rewrite `read()` to drive the identity encoder and emit the new tuple**

Find the current `read` method. Replace its body with:

```python
    def read(self):
        """Grab a frame, mirror it, submit to recognizer + face detector
        + identity encoder. Returns (frame, latest_result) where
        latest_result is
        (gesture_name, score, landmarks, face_landmarks_list, identity_emb)
        or None. `identity_emb` is a single 128-D vector (or None), from
        the largest detected face only (see design doc).
        """
        ok, frame = self._cap.read()
        if not ok:
            return None, None
        frame = cv2.flip(frame, 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts_ms = (time.monotonic_ns() - self._start_ns) // 1_000_000
        self._recognizer.recognize_async(mp_image, ts_ms)
        self._embedder.submit(mp_image, ts_ms)

        # Pick the largest detected face by bbox area and submit (rgb,
        # bbox) to the dlib worker. The worker rate-limits itself.
        face_lms, _ = self._embedder.latest()
        if face_lms:
            largest_bbox = None
            largest_area = -1
            for lms in face_lms:
                bbox = landmarks_to_bbox(lms, frame.shape)
                if bbox is None:
                    continue
                top, right, bottom, left = bbox
                area = max(0, right - left) * max(0, bottom - top)
                if area > largest_area:
                    largest_area = area
                    largest_bbox = bbox
            if largest_bbox is not None:
                self._identity.submit(rgb, largest_bbox)

        identity_emb, _ = self._identity.latest()

        with self._lock:
            latest = self._latest
        if latest is None:
            return frame, None
        gesture_name, score, landmarks = latest
        return frame, (gesture_name, score, landmarks, face_lms, identity_emb)
```

- [ ] **Step 6: Smoke-test the imports**

```bash
python -c "from handvol.capture import GestureSource; print('ok')"
```
Expected: `ok`.

- [ ] **Step 7: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all tests still pass (no new tests; capture.py has no unit tests of its own).

- [ ] **Step 8: Commit**

```bash
git add handvol/capture.py
git commit -m "feat(face): drive IdentityEncoder from GestureSource; emit largest-face identity"
```

---

## Task 7: Update `handvol.pyw` for the new tuple shape + startup check

**Files:**
- Modify: `handvol.pyw`

- [ ] **Step 1: Add `face_recognition` startup availability check**

Read `handvol.pyw`. Find the existing block in `main()`:

```python
    face_model_path = MODEL_PATH.parent / FACE_MODEL_FILENAME
    if not face_model_path.exists():
        raise SystemExit(
            f"Missing face landmarker model at {face_model_path}\n"
            "Download from: https://storage.googleapis.com/mediapipe-models/"
            "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
        )
```

After that block, add:

```python
    try:
        import face_recognition  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: face_recognition\n"
            f"Underlying error: {exc}\n"
            "Install a prebuilt dlib wheel for Windows, then run "
            "`pip install -r requirements.txt`. See README for details."
        )
```

- [ ] **Step 2: Update the result-tuple unpacking and matching logic in `capture_loop`**

Find this block in `handvol.pyw`:

```python
            if latest is None:
                gesture, score, landmarks, face_embs, face_lms = (
                    "None", 0.0, None, [], []
                )
            else:
                gesture, score, landmarks, face_embs, face_lms = latest

            profile = profile_state["profile"]
            max_similarity = None  # for the overlay readout
            if profile is None or profile.capture_count == 0:
                recognized = False
            elif not face_embs:
                no_face_streak += 1
                recognized = last_recognized if no_face_streak < NO_FACE_GRACE_FRAMES else False
            else:
                no_face_streak = 0
                # Spec: if ANY face in frame matches the profile, unlock.
                # Compute max similarity across all detected faces so we
                # can show the user the score for tuning purposes.
                sims = [profile.matches(e)[1] for e in face_embs]
                max_similarity = max(sims)
                recognized = max_similarity >= MATCH_THRESHOLD
            last_recognized = recognized
```

Replace it with:

```python
            if latest is None:
                gesture, score, landmarks, face_lms, identity_emb = (
                    "None", 0.0, None, [], None
                )
            else:
                gesture, score, landmarks, face_lms, identity_emb = latest

            profile = profile_state["profile"]
            max_similarity = None  # for the overlay readout
            if profile is None or profile.capture_count == 0:
                recognized = False
            elif identity_emb is None:
                no_face_streak += 1
                recognized = last_recognized if no_face_streak < NO_FACE_GRACE_FRAMES else False
            else:
                no_face_streak = 0
                # Largest-face-only rule from v2 design: profile.matches
                # is invoked on the single dlib embedding produced by the
                # IdentityEncoder for the most prominent face in frame.
                is_match, max_similarity = profile.matches(identity_emb)
                recognized = is_match
            last_recognized = recognized
```

- [ ] **Step 3: Smoke-test parsing**

```bash
python -c "import ast; ast.parse(open('handvol.pyw').read()); print('parses')"
```
Expected: `parses`.

- [ ] **Step 4: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add handvol.pyw
git commit -m "feat(face): consume single identity embedding in handvol.pyw; add dlib startup check"
```

---

## Task 8: Update calibration to use synchronous dlib

**Files:**
- Modify: `handvol/calibration.py`

The per-pose capture switches from `embedder.latest()` to a direct synchronous `compute_identity_embedding(rgb, bbox)` call on the most recent frame with a MediaPipe-detected face. The dot overlay still uses MediaPipe landmarks, so that logic stays.

- [ ] **Step 1: Read `handvol/calibration.py`**

Use the Read tool. Find the imports block and the `_capture_pose` function.

- [ ] **Step 2: Update imports**

Find:

```python
from handvol.face_detect import FaceEmbedder
from handvol.face_profile import FaceProfile, DEFAULT_PROFILE_PATH
from handvol.overlay import draw_face_landmarks
```

Replace with:

```python
from handvol.face_detect import FaceEmbedder, landmarks_to_bbox
from handvol.face_identity import compute_identity_embedding
from handvol.face_profile import FaceProfile, DEFAULT_PROFILE_PATH
from handvol.overlay import draw_face_landmarks
```

- [ ] **Step 3: Rewrite the `_capture_pose` body**

Find `_capture_pose`. Replace its full body with:

```python
def _capture_pose(cap, embedder, label, instruction, idx, total):
    """Run countdown then collect a single dlib embedding for this pose.

    Returns the embedding, or None if the user pressed Q.
    Retries forever within the timeout if no face is detected.
    """
    countdown_start = time.monotonic()
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts_ms = int(time.monotonic_ns() // 1_000_000)
        embedder.submit(mp_image, ts_ms)

        # Pull the most recent MediaPipe result so we can draw the dot
        # overlay and (when ready) build a bbox for dlib.
        face_lms, _ = embedder.latest()
        if face_lms:
            draw_face_landmarks(frame, face_lms)

        elapsed = time.monotonic() - countdown_start

        if elapsed < COUNTDOWN_SECONDS:
            remaining = COUNTDOWN_SECONDS - elapsed
            _draw_pose_screen(
                frame, label, instruction, idx, len(POSES),
                f"Hold still... {remaining:.1f}", (60, 220, 240),
            )
        else:
            if face_lms:
                # Use the first detected face (user is alone during
                # calibration). Compute bbox + synchronous dlib encode.
                bbox = landmarks_to_bbox(face_lms[0], frame.shape)
                emb = compute_identity_embedding(rgb, bbox) if bbox else None
                if emb is not None:
                    _draw_pose_screen(
                        frame, label, instruction, idx, len(POSES),
                        "Captured!", (80, 220, 120),
                    )
                    cv2.imshow(WINDOW_TITLE, frame)
                    cv2.waitKey(250)  # brief confirmation flash
                    return emb
                # bbox existed but dlib couldn't encode — treat as
                # "no face" and keep trying.
                if elapsed > COUNTDOWN_SECONDS + PER_POSE_TIMEOUT_SECONDS:
                    countdown_start = time.monotonic()
                    continue
                _draw_pose_screen(
                    frame, label, instruction, idx, len(POSES),
                    "Encoding failed — adjust position", (80, 80, 240),
                )
            else:
                # No MediaPipe face yet — keep trying until timeout,
                # then restart countdown.
                if elapsed > COUNTDOWN_SECONDS + PER_POSE_TIMEOUT_SECONDS:
                    countdown_start = time.monotonic()
                    continue
                _draw_pose_screen(
                    frame, label, instruction, idx, len(POSES),
                    "No face detected - adjust position", (80, 80, 240),
                )

        cv2.imshow(WINDOW_TITLE, frame)
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            return None
```

- [ ] **Step 4: Smoke-test the imports and pose list**

```bash
python -c "from handvol.calibration import run_calibration, POSES; print(len(POSES))"
```
Expected: `20`.

- [ ] **Step 5: Run the full suite — confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add handvol/calibration.py
git commit -m "feat(face): calibration captures dlib embeddings synchronously per pose"
```

---

## Task 9: Manual end-to-end testing & threshold tuning

This task has no code changes. It is an explicit checklist for the implementer to walk through with the real camera. If any step fails, file the failure mode as a follow-up task rather than silently relaxing thresholds.

- [ ] **Step 1: Fresh state — confirm v1 profile rejection**

If you have an old `data/face_profile.npz` from before the version bump:

```bash
ls -la data/face_profile.npz
```

Launch `python handvol.pyw --show`. Expected behavior:
- Tray icon appears.
- Preview overlay shows **NO PROFILE** (gray) in the top right.
- Log/console contains a warning like `face profile at ... is version 1; this build expects version 2`.

If you do not have an old profile, just confirm the preview opens with **NO PROFILE**.

- [ ] **Step 2: Run calibration via the tray menu**

Right-click the tray icon → **Calibrate face...**. Expected:
- HandVol preview closes (worker stopped, camera released).
- Calibration window opens; 20 poses run; each shows a 2s countdown and captures one **dlib** embedding (not a MediaPipe landmark vector).
- After the last pose, calibration window closes; HandVol worker restarts automatically; `data/face_profile.npz` exists at v2.

- [ ] **Step 3: Verify unlocked behavior + similarity readout**

With only yourself in the frame:
- Preview overlay shows **UNLOCKED** (green) in the top right.
- The small `0.xx / 0.92` line beneath should sit at **0.93-0.97** for neutral expression.
- All existing gestures still work (point→scrub, fist→mute, palm→play/pause, victory→Spotify, OK sign→scrub, thumbs sideways→next/prev, ILoveYou→close Spotify).

- [ ] **Step 4: Verify expression robustness**

Smile, frown, talk normally. Expected:
- Similarity should dip slightly (~0.88-0.95) but stay above threshold.
- Gestures should not flicker between recognized/unrecognized.

- [ ] **Step 5: Verify lockout when face is occluded**

Cover your face (with the other hand, a book, etc.). Expected:
- After ~500ms, overlay flips to **LOCKED** (red).
- Gestures stop firing.

- [ ] **Step 6: Verify lockout with a different person**

If a second person is available, have them stand in frame:
- Overlay shows **LOCKED**; their gestures are ignored.
- Similarity readout should drop to **0.4-0.7** (a clear gap from your own scores).

If their score and yours overlap (e.g., both near 0.85), adjust `MATCH_THRESHOLD` in `handvol/face_profile.py`:
- False positives (a stranger unlocking): raise threshold (e.g. 0.94).
- False negatives (you fail to unlock): lower threshold (e.g. 0.88).

- [ ] **Step 7: Verify "largest face wins" rule**

If a second person is available: stand together in frame. Move so the second person is closer/larger than you. Expected:
- Overlay shows **LOCKED** (because the largest face is not yours).
- Similarity readout reflects the OTHER person's similarity to you (probably 0.4-0.7).
- When you move forward so you are the largest face, **UNLOCKED** returns.

- [ ] **Step 8: Verify main-loop FPS is unaffected**

Open the preview; the bottom-right FPS readout should sit near ~30. Engage SCRUB (point-up and move). Volume changes should feel smooth, identical to before the dlib swap. There should be no perceptible stutter from dlib running on the worker thread.

- [ ] **Step 9: Run the full unit suite one more time**

```bash
python -m pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 10: Commit any threshold tuning**

If you changed `MATCH_THRESHOLD` during Step 6:

```bash
git add handvol/face_profile.py
git commit -m "tune(face): adjust MATCH_THRESHOLD after dlib calibration testing"
```

---

## Done Criteria

- All unit tests pass (`python -m pytest tests/ -q`).
- Manual checklist (Task 9) passes end-to-end.
- `data/face_profile.npz` v2 exists and is gitignored.
- README documents the dlib install step.
- Branch is ready to merge to `main`.
