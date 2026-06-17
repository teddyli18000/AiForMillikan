from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = _resolve_config_path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")
    _apply_environment_overrides(data)
    return data


def _resolve_config_path(path: str | Path) -> Path:
    config_path = Path(path)
    if config_path.exists():
        return config_path
    default_config = os.environ.get("MILLIKAN_DEFAULT_CONFIG")
    if default_config and str(path).replace("\\", "/") in {"configs/default.yaml", "configs/default.yml"}:
        return Path(default_config)
    return config_path


def _apply_environment_overrides(config: dict[str, Any]) -> None:
    run_root = os.environ.get("MILLIKAN_RUN_ROOT")
    if not run_root:
        return
    project = config.setdefault("project", {})
    if isinstance(project, dict):
        project["run_root"] = str(Path(run_root))


def deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_update(result[key], value)
        else:
            result[key] = value
    return result


def save_config(config: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

