"""GestureSource.open() failure path. Fakes cv2.VideoCapture so no real camera
opens, and fails before MediaPipe is ever built."""

import pytest

import handvol.capture as capture


class FakeCapture:
    instances = []

    def __init__(self, index, api):
        self.index = index
        self.api = api
        self.released = False
        FakeCapture.instances.append(self)

    def isOpened(self):
        return False

    def release(self):
        self.released = True


def test_open_raises_camera_open_error_and_releases(monkeypatch):
    FakeCapture.instances = []
    monkeypatch.setattr(capture.cv2, "VideoCapture", FakeCapture)

    def no_mediapipe(*a, **kw):
        raise AssertionError("MediaPipe must not be built when the camera fails")

    monkeypatch.setattr(capture.mp_vision.GestureRecognizer,
                        "create_from_options", no_mediapipe)

    source = capture.GestureSource(cam_index=3)
    with pytest.raises(capture.CameraOpenError):
        source.open()

    assert len(FakeCapture.instances) == 1
    fake = FakeCapture.instances[0]
    assert fake.index == 3
    assert fake.api == capture.cv2.CAP_DSHOW
    assert fake.released is True
    assert source._cap is None
    assert source._recognizer is None
