from __future__ import annotations

from pathlib import Path

from millikan_ai.config import load_config


def test_packaged_default_config_falls_back_to_environment(tmp_path, monkeypatch):
    bundled_config = tmp_path / "resources" / "configs" / "default.yaml"
    bundled_config.parent.mkdir(parents=True)
    bundled_config.write_text("project:\n  run_root: runs\nphysics:\n  gravity_m_s2: 9.8\n", encoding="utf-8")
    run_root = tmp_path / "user-data" / "runs"
    monkeypatch.setenv("MILLIKAN_DEFAULT_CONFIG", str(bundled_config))
    monkeypatch.setenv("MILLIKAN_RUN_ROOT", str(run_root))
    monkeypatch.chdir(tmp_path)

    config = load_config("configs/default.yaml")

    assert config["physics"]["gravity_m_s2"] == 9.8
    assert config["project"]["run_root"] == str(run_root)
