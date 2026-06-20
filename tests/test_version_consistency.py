from __future__ import annotations

import json
from pathlib import Path

import millikan_ai


ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "1.0.0"


def test_python_and_desktop_versions_match_release() -> None:
    package = json.loads((ROOT / "apps" / "desktop" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "apps" / "desktop" / "package-lock.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert millikan_ai.__version__ == RELEASE_VERSION
    assert package["version"] == RELEASE_VERSION
    assert package_lock["version"] == RELEASE_VERSION
    assert package_lock["packages"][""]["version"] == RELEASE_VERSION
    assert f'version = "{RELEASE_VERSION}"' in pyproject
