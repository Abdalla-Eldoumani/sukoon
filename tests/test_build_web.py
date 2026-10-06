import importlib.util
import io
import sys

from tests.conftest import ROOT


def test_copy_works_from_a_folder_with_arabic_letters_on_a_cp1252_terminal(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_web", ROOT / "scripts" / "build_web.py")
    build_web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_web)
    root = tmp_path / "تجربة سكون"
    (root / "web" / "dist").mkdir(parents=True)
    (root / "web" / "dist" / "index.html").write_text("<!doctype html>")
    monkeypatch.setattr(build_web, "ROOT", root)
    monkeypatch.setattr(build_web, "DIST", root / "web" / "dist")
    monkeypatch.setattr(build_web, "TARGET", root / "src" / "sukoon" / "web_dist")
    # Git Bash on Windows hands Python a cp1252 stdout.
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    assert build_web.main(["--copy-only"]) == 0
    assert (root / "src" / "sukoon" / "web_dist" / "index.html").is_file()
