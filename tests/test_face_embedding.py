import numpy as np
import pytest

from handvol.face_detect import landmarks_to_embedding


class _LM:
    """Minimal stand-in for MediaPipe's NormalizedLandmark."""
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


def _make_landmarks(n=478, scale=1.0, offset=(0.0, 0.0)):
    """Generate n landmarks on a deterministic grid for testing."""
    rng = np.random.default_rng(seed=0)
    pts = rng.uniform(-0.5, 0.5, size=(n, 3)) * scale
    pts[:, 0] += offset[0]
    pts[:, 1] += offset[1]
    return [_LM(p[0], p[1], p[2]) for p in pts]


def test_returns_none_for_missing_landmarks():
    assert landmarks_to_embedding(None) is None
    assert landmarks_to_embedding([]) is None


def test_returns_none_for_too_few_landmarks():
    assert landmarks_to_embedding(_make_landmarks(n=10)) is None


def test_embedding_shape_is_flat_vector():
    lms = _make_landmarks(n=478)
    emb = landmarks_to_embedding(lms)
    assert emb is not None
    assert emb.ndim == 1
    assert emb.shape[0] == 478 * 3


def test_embedding_is_translation_invariant():
    base = _make_landmarks(n=478, offset=(0.0, 0.0))
    shifted = _make_landmarks(n=478, offset=(0.2, -0.1))  # same rng seed -> same pattern
    e1 = landmarks_to_embedding(base)
    e2 = landmarks_to_embedding(shifted)
    # Cosine similarity should be ~1.0 after centroid removal.
    cos = float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)))
    assert cos == pytest.approx(1.0, abs=1e-6)


def test_embedding_is_scale_invariant():
    base = _make_landmarks(n=478, scale=1.0)
    bigger = _make_landmarks(n=478, scale=2.5)  # same rng seed -> same pattern, scaled
    e1 = landmarks_to_embedding(base)
    e2 = landmarks_to_embedding(bigger)
    cos = float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)))
    assert cos == pytest.approx(1.0, abs=1e-6)
