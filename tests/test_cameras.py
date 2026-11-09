"""Pure-function tests for handvol.cameras. Never touches real COM or cameras."""

import handvol.cameras as cameras


def test_choose_camera_skips_leading_virtual_camera():
    names = ["Phone (Windows Virtual Camera)", "NexiGo N60 FHD Webcam"]
    assert cameras.choose_camera(names) == 1


def test_choose_camera_prefers_saved_name():
    names = ["A (Windows Virtual Camera)", "OBS Virtual Camera", "NexiGo N60 FHD Webcam"]
    assert cameras.choose_camera(names, saved_name="NexiGo N60 FHD Webcam") == 2


def test_choose_camera_missing_saved_name_falls_through_to_first_non_virtual():
    names = ["OBS Virtual Camera", "Camera (NVIDIA Broadcast)", "NexiGo N60 FHD Webcam"]
    assert cameras.choose_camera(names, saved_name="Gone Camera") == 1


def test_choose_camera_cli_index_wins_over_saved_name():
    names = ["A", "B", "NexiGo N60 FHD Webcam", "C"]
    assert cameras.choose_camera(names, saved_name="NexiGo N60 FHD Webcam", cli_index=3) == 3


def test_choose_camera_all_virtual_returns_zero():
    names = ["OBS Virtual Camera", "Windows Virtual Camera"]
    assert cameras.choose_camera(names) == 0


def test_choose_camera_empty_list_returns_zero():
    assert cameras.choose_camera([]) == 0


def test_choose_camera_duplicate_names_resolve_to_first_match():
    assert cameras.choose_camera(["Cam", "Cam"], saved_name="Cam") == 0


def test_is_virtual_detects_obs():
    assert cameras.is_virtual("OBS Virtual Camera") is True


def test_is_virtual_ignores_physical_camera():
    assert cameras.is_virtual("Camera (NVIDIA Broadcast)") is False


def test_list_cameras_returns_empty_list_when_enumeration_raises(monkeypatch, capsys):
    def boom():
        raise OSError("boom")

    monkeypatch.setattr(cameras, "_enumerate_dshow", boom)
    assert cameras.list_cameras() == []
    assert "camera enumeration failed" in capsys.readouterr().out
