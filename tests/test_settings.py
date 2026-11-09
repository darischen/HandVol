"""Tests for handvol.settings. Uses tmp_path so no real settings file is touched."""

import handvol.settings as settings


def test_load_missing_file_returns_empty_dict(tmp_path):
    assert settings.load(tmp_path / "missing.json") == {}


def test_load_malformed_json_returns_empty_dict(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert settings.load(p) == {}


def test_load_non_dict_json_returns_empty_dict(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert settings.load(p) == {}


def test_update_then_load_round_trips_and_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "HandVol" / "settings.json"
    assert settings.update({"camera_name": "X"}, p) is True
    assert settings.load(p) == {"camera_name": "X"}


def test_update_merges_into_existing_settings(tmp_path):
    p = tmp_path / "settings.json"
    settings.update({"a": 1}, p)
    settings.update({"b": 2}, p)
    assert settings.load(p) == {"a": 1, "b": 2}


def test_update_returns_false_when_parent_is_a_file(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file", encoding="utf-8")
    p = blocker / "settings.json"
    assert settings.update({"a": 1}, p) is False
    assert "could not save settings" in capsys.readouterr().out
