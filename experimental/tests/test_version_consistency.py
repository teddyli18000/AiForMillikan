from __future__ import annotations

import json
from pathlib import Path

import millikan_ai


ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    raise AssertionError("pyproject.toml has no version line")


def test_python_and_desktop_versions_match_release() -> None:
    version = _pyproject_version()
    package = json.loads((ROOT / "apps" / "desktop" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "apps" / "desktop" / "package-lock.json").read_text(encoding="utf-8"))

    assert millikan_ai.__version__ == version
    assert package["version"] == version
    assert package_lock["version"] == version
    assert package_lock["packages"][""]["version"] == version
