import sys
import uuid
from pathlib import Path

import pytest

from sukoon.settings import Settings, UnsafePathError, default_home


def test_sukoon_home_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("SUKOON_HOME", str(tmp_path / "here"))
    assert default_home() == tmp_path / "here"


def test_linux_falls_back_to_xdg_then_local_share(monkeypatch, tmp_path):
    monkeypatch.delenv("SUKOON_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_home() == tmp_path / "sukoon"
    monkeypatch.delenv("XDG_DATA_HOME")
    assert default_home() == Path.home() / ".local" / "share" / "sukoon"


def test_windows_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("SUKOON_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_home() == tmp_path / "sukoon"


def test_ensure_dirs_creates_every_area(tmp_path):
    s = Settings(home=tmp_path / "data")
    s.ensure_dirs()
    assert sorted(p.name for p in s.home.iterdir()) == ["models", "outputs", "uploads", "work"]


def test_limits_match_the_spec(tmp_path):
    s = Settings(home=tmp_path)
    assert s.max_upload_bytes == 8 * 1024**3
    assert s.max_duration_s == 6 * 3600
    assert s.max_queued == 50
    assert (s.port_first, s.port_last) == (8417, 8427)


def test_job_path_joins_a_uuid_onto_an_area(tmp_path):
    s = Settings(home=tmp_path)
    job = str(uuid.uuid4())
    assert s.job_path("work", job) == tmp_path.resolve() / "work" / job


@pytest.mark.parametrize(
    "job_id",
    [
        "../../etc",
        "..",
        "",
        "a/b",
        "urn:uuid:12345678-1234-5678-1234-567812345678",
        "{12345678-1234-5678-1234-567812345678}",
        "12345678123456781234567812345678",
    ],
)
def test_job_path_refuses_anything_but_a_canonical_uuid(tmp_path, job_id):
    with pytest.raises(UnsafePathError):
        Settings(home=tmp_path).job_path("work", job_id)


def test_job_path_refuses_unknown_area(tmp_path):
    with pytest.raises(UnsafePathError):
        Settings(home=tmp_path).job_path("..", str(uuid.uuid4()))  # type: ignore[arg-type]


def link_folder(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        # Windows without the symlink privilege; a junction needs none and resolves the same way.
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


def test_job_path_refuses_a_symlinked_job_folder(tmp_path):
    s = Settings(home=tmp_path / "data")
    s.ensure_dirs()
    job = str(uuid.uuid4())
    link_folder(s.home / "work" / job, tmp_path)
    with pytest.raises(UnsafePathError):
        s.job_path("work", job)


def test_arabic_home_with_spaces(tmp_path):
    s = Settings(home=tmp_path / "مجلد البيانات")
    s.ensure_dirs()
    assert (s.home / "uploads").is_dir()
