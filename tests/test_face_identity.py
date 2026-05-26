import time

import numpy as np

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
