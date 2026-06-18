from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import normal_config
from .grid import calibrate_grid
from .inversion import run_weighted_integer_inversion
from .physics import compute_q, fit_zero_v_velocity
from .tracking import TrackRequest, run_tracking
from .video import file_sha256, file_url, inspect_video
from .voltage import suggest_zero_v_window


def initialize_session(session_root: str | None = None, run_root: str | None = None, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    root = Path(session_root or cfg["session"]["session_root"])
    run = Path(run_root or cfg["session"]["run_root"])
    root.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    path = root / "normal_session.json"
    if path.exists():
        session = _read_json(path)
    else:
        session = {
            "schema_version": 1,
            "session_id": f"normal_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            "created_at": _now(),
            "updated_at": _now(),
            "records": [],
            "active_video": None,
            "inversion": None,
        }
        _write_json(path, session)
    return {"session": _public_session(session), "session_file": str(path), "session_root": str(root), "run_root": str(run), "config": cfg}


def prepare_video(video_path: str, session_root: str | None = None, run_root: str | None = None, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    init = initialize_session(session_root, run_root, config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    metadata = inspect_video(video_path)
    if not metadata.get("readable"):
        raise RuntimeError(f"video is not readable: {video_path}")
    boundary = suggest_zero_v_window(video_path, cfg)
    suggestion = boundary["suggestion"]
    grid = calibrate_grid(video_path, cfg, start_frame=int(suggestion.get("zero_v_start_frame", 0)), end_frame=int(suggestion.get("zero_v_end_frame", metadata["frame_count"] - 1)))
    session["active_video"] = {
        "path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary": suggestion,
        "grid": grid,
        "prepared_at": _now(),
    }
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {
        "session_root": init["session_root"],
        "video_path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary": boundary,
        "grid": grid,
        "session": _public_session(session),
    }


def save_measurement(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    init = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    record_id = f"rec_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    record_dir = Path(init["session_root"]) / "records" / record_id
    record_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(payload["video_path"])
    metadata = inspect_video(video_path)
    boundary = _normalize_boundary(payload["boundary"], metadata)
    grid = payload.get("grid") or {}
    target = payload["target"]
    overrides = payload.get("parameter_overrides") or {}
    effective_cfg = normal_config(overrides if isinstance(overrides, dict) else None)
    if not grid.get("valid"):
        record = _diagnostic_record(record_id, video_path, boundary, target, grid, ["grid_calibration_invalid"], record_dir)
    else:
        tracking = run_tracking(
            TrackRequest(
                video_path=video_path,
                target_frame=int(target["target_frame"]),
                zero_v_start_frame=int(boundary["zero_v_start_frame"]),
                zero_v_end_frame=int(boundary["zero_v_end_frame"]),
                source_center=(float(target["source_center"]["x"]), float(target["source_center"]["y"])),
                grid=grid,
                run_dir=str(record_dir),
                config=effective_cfg,
            )
        )
        fit = fit_zero_v_velocity(tracking["track"], float(metadata.get("fps") or tracking["fps"] or 30.0), float(grid["scale_y_m_per_px"]), effective_cfg)
        q = compute_q(fit, float(payload["balance_voltage_V"]), effective_cfg)
        status = "valid" if q.get("valid") and fit.get("valid") else "diagnostic"
        record = {
            "schema_version": 1,
            "record_id": record_id,
            "created_at": _now(),
            "video_path": video_path,
            "video_sha256_16": file_sha256(video_path)[:16] if Path(video_path).exists() else "",
            "metadata": metadata,
            "balance_voltage_V": float(payload["balance_voltage_V"]),
            "time_window": boundary,
            "target": target,
            "grid": grid,
            "parameter_overrides": overrides,
            "effective_parameters": effective_cfg["physics"],
            "tracking": {"stats": _tracking_stats(tracking["track"]), "artifacts": _artifact_paths(tracking)},
            "crossing_events": tracking["crossing_events"],
            "fit": fit,
            "q": q,
            "status": status,
            "kept": status == "valid",
            "record_dir": str(record_dir),
            "recovery_suggestions": q.get("recovery_suggestions") or fit.get("recovery_suggestions") or [],
        }
        _write_json(record_dir / "q_result.json", q)
    _write_json(record_dir / "record_manifest.json", record)
    session.setdefault("records", []).append(record)
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {"session_root": init["session_root"], "record": _public_record(record), "session": _public_session(session)}


def update_record_selection(session_root: str | None, record_id: str, kept: bool) -> dict[str, Any]:
    init = initialize_session(session_root)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    for record in session.get("records", []):
        if record.get("record_id") == record_id:
            record["kept"] = bool(kept) and record.get("status") == "valid"
            break
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {"session": _public_session(session)}


def run_inversion(session_root: str | None = None, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    init = initialize_session(session_root, config_overrides=config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    inversion = run_weighted_integer_inversion(session.get("records", []), cfg)
    inversion["created_at"] = _now()
    session["inversion"] = inversion
    session["updated_at"] = _now()
    _write_json(session_path, session)
    _write_json(Path(init["session_root"]) / "normal_inversion.json", inversion)
    return {"session_root": init["session_root"], "inversion": inversion, "session": _public_session(session)}


def export_session(session_root: str | None, export_root: str) -> dict[str, Any]:
    init = initialize_session(session_root)
    source = Path(init["session_root"])
    session = _read_json(Path(init["session_file"]))
    destination = Path(export_root) / f"{session['session_id']}_export"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if (source / "records").exists():
        shutil.copytree(source / "records", destination / "records")
    _write_json(destination / "normal_session.json", session)
    if session.get("inversion"):
        _write_json(destination / "normal_inversion.json", session["inversion"])
    report = destination / "normal_session_report.md"
    report.write_text(render_report(session), encoding="utf-8")
    manifest = {"schema_version": 1, "session_id": session["session_id"], "exported_at": _now(), "files": sorted(str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file())}
    _write_json(destination / "export_manifest.json", manifest)
    return {"destination": str(destination), "manifest": manifest, "markdown": str(report)}


def render_report(session: dict[str, Any]) -> str:
    lines = ["# Millikan AI Normal Session Report", "", f"Session: `{session.get('session_id')}`", "", "| Record | Status | Kept | q (C) | sigma_q (C) | Video |", "| --- | --- | --- | ---: | ---: | --- |"]
    for record in session.get("records", []):
        q = record.get("q", {})
        lines.append(f"| {record.get('record_id')} | {record.get('status')} | {record.get('kept')} | {q.get('q_C', '-')} | {q.get('sigma_q_C', '-')} | {record.get('video_path', '')} |")
    if session.get("inversion"):
        lines.extend(["", "## Inversion", "", "```json", json.dumps(session["inversion"], ensure_ascii=False, indent=2), "```"])
    return "\n".join(lines) + "\n"


def _normalize_boundary(boundary: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    fps = float(metadata.get("fps") or 30.0)
    frame_count = int(metadata.get("frame_count") or 1)
    if "zero_v_start_frame" in boundary:
        start_frame = int(boundary["zero_v_start_frame"])
    else:
        start_frame = int(round(float(boundary["zero_v_start_s"]) * fps))
    if "zero_v_end_frame" in boundary:
        end_frame = int(boundary["zero_v_end_frame"])
    else:
        end_frame = int(round(float(boundary["zero_v_end_s"]) * fps))
    start_frame = max(0, min(frame_count - 1, start_frame))
    end_frame = max(start_frame, min(frame_count - 1, end_frame))
    return {
        "zero_v_start_s": start_frame / fps,
        "zero_v_end_s": end_frame / fps,
        "zero_v_start_frame": start_frame,
        "zero_v_end_frame": end_frame,
        "source": str(boundary.get("source", "manual_ui")),
    }


def _diagnostic_record(record_id: str, video_path: str, boundary: dict[str, Any], target: dict[str, Any], grid: dict[str, Any], flags: list[str], record_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_id": record_id,
        "created_at": _now(),
        "video_path": video_path,
        "time_window": boundary,
        "target": target,
        "grid": grid,
        "crossing_events": [],
        "fit": {"valid": False, "flags": flags},
        "q": {"valid": False, "diagnostic_only": True, "flags": flags},
        "status": "diagnostic",
        "kept": False,
        "record_dir": str(record_dir),
        "recovery_suggestions": ["请先修正网格识别或有效测量区。"],
    }


def _tracking_stats(track: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_points": len(track),
        "detected_points": sum(1 for row in track if row.get("detected")),
        "missing_points": sum(1 for row in track if row.get("state") == "missing"),
        "reacquired_points": sum(1 for row in track if row.get("state") == "reacquired"),
    }


def _artifact_paths(tracking: dict[str, Any]) -> dict[str, str]:
    return {key: value for key, value in tracking.items() if key.endswith("_csv") or key.endswith("_json") or key.endswith("_mp4")}


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    records = [_public_record(record) for record in session.get("records", [])]
    valid = [record for record in records if record.get("status") == "valid"]
    kept = [record for record in valid if record.get("kept")]
    return {
        "schema_version": session.get("schema_version", 1),
        "session_id": session.get("session_id"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "records": records,
        "counts": {"total": len(records), "valid": len(valid), "kept_valid": len(kept), "selected_valid": len(kept)},
        "eligible_for_inversion": len(kept) >= 3,
        "inversion": session.get("inversion"),
        "active_video": session.get("active_video"),
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in record.items() if key != "record_dir"}
    q = record.get("q") if isinstance(record.get("q"), dict) else {}
    fit = record.get("fit") if isinstance(record.get("fit"), dict) else {}
    tracking = record.get("tracking") if isinstance(record.get("tracking"), dict) else {}
    public.update(
        {
            "valid": record.get("status") == "valid",
            "q_C": q.get("q_C"),
            "charge_abs_C": q.get("charge_abs_C"),
            "sigma_q_C": q.get("sigma_q_C"),
            "radius_m": q.get("radius_m"),
            "fall_velocity_m_s": fit.get("velocity_m_s"),
            "flags": list(dict.fromkeys([*(fit.get("flags") or []), *(q.get("flags") or [])])),
            "artifacts": tracking.get("artifacts") or {},
            "crossings": record.get("crossing_events") or [],
        }
    )
    return public


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
