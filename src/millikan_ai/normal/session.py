from __future__ import annotations

import json
import math
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import normal_config
from .grid import calibrate_grid
from .inversion import run_weighted_integer_inversion
from .physics import compute_q, fit_zero_v_velocity
from .tracking import TrackRequest, make_crossing_review_clip, run_tracking
from .video import file_sha256, file_url, inspect_video
from .voltage import suggest_zero_v_window

ACTIVE_VIDEO_STATES = {
    "video_prepared",
    "boundary_confirmed",
    "target_selected",
    "tracking",
}

RECORD_STATES = {
    "pending_crossing_review",
    "pending_user_confirmation",
    "accepted",
    "diagnostic",
    "rejected_crossing_identity",
    "rejected_by_user",
}

ProgressCallback = Callable[[dict[str, Any]], None]


def initialize_session(session_root: str | None = None, run_root: str | None = None, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    session_id = f"normal_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    root = Path(session_root) if session_root else Path(cfg["session"]["session_root"]) / session_id
    run = Path(run_root or cfg["session"]["run_root"])
    root.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    path = root / "normal_session.json"
    if session_root and path.exists():
        session = _read_json(path)
    else:
        session = {
            "schema_version": 1,
            "session_id": session_id,
            "transient": True,
            "created_at": _now(),
            "updated_at": _now(),
            "records": [],
            "active_video": None,
            "inversion": None,
        }
        _write_json(path, session)
    return {
        "session": _public_session(session, str(root)),
        "session_file": str(path),
        "session_root": str(root),
        "run_root": str(run),
        "config": cfg,
    }


def inspect_video_only(video_path: str) -> dict[str, Any]:
    metadata = inspect_video(video_path)
    if not metadata.get("readable"):
        raise RuntimeError(f"video is not readable: {video_path}")
    return {"video_path": video_path, "metadata": metadata, "video_url": file_url(video_path)}


def prepare_video(
    video_path: str,
    session_root: str | None = None,
    run_root: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    init = initialize_session(session_root, run_root, config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)

    _emit(progress_callback, "inspect_metadata", "读取视频元数据", indeterminate=True)
    metadata = inspect_video(video_path)
    if not metadata.get("readable"):
        raise RuntimeError(f"video is not readable: {video_path}")

    boundary = suggest_zero_v_window(video_path, cfg, _stage_emitter(progress_callback))
    suggestion = boundary["suggestion"]
    _emit(progress_callback, "detect_visual_changes", "检测画面变化", indeterminate=True)
    _emit(progress_callback, "suggest_zero_v_window", "生成 0V 时间建议", indeterminate=True)
    grid = calibrate_grid(
        video_path,
        cfg,
        start_frame=int(suggestion.get("zero_v_start_frame", 0)),
        end_frame=int(suggestion.get("zero_v_end_frame", metadata["frame_count"] - 1)),
        progress_callback=_stage_emitter(progress_callback),
    )
    _emit(progress_callback, "detect_grid_lines", "识别网格线", indeterminate=True)

    session["active_video"] = {
        "state": "video_prepared",
        "path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary_suggestion": suggestion,
        "boundary": None,
        "grid": grid,
        "prepared_at": _now(),
    }
    session["updated_at"] = _now()
    _write_json(session_path, session)
    _emit(progress_callback, "ready_for_boundary_review", "等待用户确认 0V 起止时间", indeterminate=True)
    return {
        "session_root": init["session_root"],
        "video_path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary": suggestion,
        "boundary_diagnostics": {"samples": boundary.get("samples", []), "operations": boundary.get("operations", [])},
        "grid": grid,
        "session": _public_session(session, init["session_root"]),
        "config": cfg,
    }


def confirm_boundary(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    init = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    active = _require_active_state(session, {"video_prepared", "boundary_confirmed"})
    metadata = active["metadata"]
    boundary = _normalize_boundary(payload["boundary"], metadata)
    boundary["selection_window"] = _selection_window(boundary, metadata, cfg)
    active["boundary"] = boundary
    active["state"] = "boundary_confirmed"
    active["boundary_confirmed_at"] = _now()
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {"session_root": init["session_root"], "active_video": active, "session": _public_session(session, init["session_root"])}


def select_target(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    init = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    active = _require_active_state(session, {"boundary_confirmed"})
    if not bool(payload.get("balance_confirmed")):
        raise RuntimeError("balance_confirmed is required before target selection")
    voltage = float(payload.get("balance_voltage_V", math.nan))
    if not math.isfinite(voltage) or voltage <= 0:
        raise RuntimeError("positive balance_voltage_V is required")
    target = _normalize_target(payload["target"], active["metadata"])
    boundary = active["boundary"]
    target_frame = int(target["target_frame"])
    window = boundary.get("selection_window") or _selection_window(boundary, active["metadata"], normal_config(config_overrides))
    if not (int(window["start_frame"]) <= target_frame <= int(window["end_frame"])):
        raise RuntimeError("target frame must be inside the selection window near 0V start")
    overrides = payload.get("parameter_overrides") or {}
    target["selection_window"] = window
    active["target"] = target
    active["retry_of_record_id"] = payload.get("retry_of_record_id")
    active["balance_voltage_V"] = voltage
    active["balance_confirmed"] = True
    active["parameter_overrides"] = overrides if isinstance(overrides, dict) else {}
    active["state"] = "target_selected"
    active["target_selected_at"] = _now()
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {"session_root": init["session_root"], "active_video": active, "session": _public_session(session, init["session_root"])}


def save_measurement(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    init = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    active = _require_active_state(session, {"target_selected"})
    active["state"] = "tracking"
    session["updated_at"] = _now()
    _write_json(session_path, session)

    record_id = f"rec_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    record_dir = Path(init["session_root"]) / "records" / record_id
    record_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(active["path"])
    metadata = active["metadata"]
    boundary = active["boundary"]
    grid = active["grid"]
    target = active["target"]
    overrides = active.get("parameter_overrides") or {}
    effective_cfg = normal_config(overrides if isinstance(overrides, dict) else None)

    _emit(progress_callback, "validate_measurement_inputs", "校验测量输入", indeterminate=True)
    if not grid.get("valid"):
        record = _diagnostic_record(record_id, video_path, boundary, target, grid, ["grid_calibration_invalid"], record_dir, active, effective_cfg)
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
            ),
            progress_callback=_stage_emitter(progress_callback),
        )
        _emit(progress_callback, "fit_velocity", "拟合 0V 下落速度", indeterminate=True)
        fit = fit_zero_v_velocity(tracking["track"], float(metadata.get("fps") or tracking["fps"] or 30.0), float(grid["scale_y_m_per_px"]), effective_cfg)
        _emit(progress_callback, "compute_q", "计算 q 和不确定度", indeterminate=True)
        q = compute_q(fit, float(active["balance_voltage_V"]), effective_cfg)
        q_ok = bool(q.get("valid") and fit.get("valid"))
        crossings = tracking["crossing_events"]
        if not q_ok:
            status = "diagnostic"
        elif crossings:
            status = "pending_crossing_review"
        else:
            status = "pending_user_confirmation"
        record = {
            "schema_version": 1,
            "record_id": record_id,
            "retry_of_record_id": active.get("retry_of_record_id"),
            "created_at": _now(),
            "video_path": video_path,
            "video_sha256_16": file_sha256(video_path)[:16] if Path(video_path).exists() else "",
            "metadata": metadata,
            "balance_voltage_V": float(active["balance_voltage_V"]),
            "balance_confirmed": True,
            "time_window": boundary,
            "target": target,
            "grid": grid,
            "parameter_overrides": overrides,
            "effective_parameters": {"physics": effective_cfg["physics"], "grid": effective_cfg["grid"]},
            "tracking": {"stats": _tracking_stats(tracking["track"]), "artifacts": _artifact_paths(tracking), "track": tracking["track"]},
            "crossing_events": crossings,
            "fit": fit,
            "q": q,
            "status": status,
            "kept": False,
            "record_dir": str(record_dir),
            "recovery_suggestions": q.get("recovery_suggestions") or fit.get("recovery_suggestions") or [],
        }
        _write_json(record_dir / "q_result.json", q)

    _write_json(record_dir / "record_manifest.json", record)
    session.setdefault("records", []).append(record)
    active["last_record_id"] = record_id
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {"session_root": init["session_root"], "record": _public_record(record), "session": _public_session(session, init["session_root"])}


def prepare_crossing_review(payload: dict[str, Any]) -> dict[str, Any]:
    init = initialize_session(payload.get("session_root"))
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    record = _find_record(session, str(payload["record_id"]))
    event = _find_crossing(record, str(payload["event_id"]))
    record_dir = Path(record["record_dir"])
    clip = record_dir / "crossing_reviews" / f"{event['event_id']}.mp4"
    if not clip.exists():
        review = make_crossing_review_clip(record["video_path"], event, clip)
        event["review_clip_path"] = review["clip_path"]
        event["review_clip_url"] = file_url(review["clip_path"])
        event["review_source_video_box"] = review["source_video_box"]
        event["review_clip_start_time_s"] = review["start_time_s"]
        event["review_clip_end_time_s"] = review["end_time_s"]
    else:
        event["review_clip_path"] = str(clip)
        event["review_clip_url"] = file_url(clip)
    session["updated_at"] = _now()
    _write_json(session_path, session)
    _write_json(record_dir / "record_manifest.json", record)
    return {"session_root": init["session_root"], "record": _public_record(record), "event": event, "session": _public_session(session, init["session_root"])}


def review_crossing(payload: dict[str, Any]) -> dict[str, Any]:
    result = str(payload.get("result") or "")
    if result not in {"same_drop", "different_drop"}:
        raise RuntimeError("crossing review result must be same_drop or different_drop")
    init = initialize_session(payload.get("session_root"))
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    record = _find_record(session, str(payload["record_id"]))
    event = _find_crossing(record, str(payload["event_id"]))
    event["review_result"] = result
    event["reviewed_at"] = _now()
    if result == "different_drop":
        record["status"] = "rejected_crossing_identity"
        record["kept"] = False
        _restore_active_for_adjustment(session, record)
    elif record.get("status") == "pending_crossing_review" and _all_crossings_reviewed_same(record):
        record["status"] = "pending_user_confirmation"
    session["updated_at"] = _now()
    _write_json(session_path, session)
    _write_json(Path(record["record_dir"]) / "record_manifest.json", record)
    return {"session_root": init["session_root"], "record": _public_record(record), "session": _public_session(session, init["session_root"])}


def update_record_selection(session_root: str | None, record_id: str, kept: bool) -> dict[str, Any]:
    init = initialize_session(session_root)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    record = _find_record(session, record_id)
    if kept:
        if record.get("status") == "accepted":
            record["kept"] = True
        elif record.get("status") == "pending_user_confirmation" and _all_crossings_reviewed_same(record) and bool((record.get("q") or {}).get("valid")):
            record["status"] = "accepted"
            record["kept"] = True
            record["accepted_at"] = _now()
        else:
            raise RuntimeError(f"record cannot be accepted from status={record.get('status')}")
    else:
        record["status"] = "rejected_by_user"
        record["kept"] = False
        _restore_active_for_adjustment(session, record)
    session["updated_at"] = _now()
    _write_json(session_path, session)
    _write_json(Path(record["record_dir"]) / "record_manifest.json", record)
    return {"session": _public_session(session, init["session_root"])}


def run_inversion(session_root: str | None = None, config_overrides: dict[str, Any] | None = None, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    init = initialize_session(session_root, config_overrides=config_overrides)
    session_path = Path(init["session_file"])
    session = _read_json(session_path)
    _emit(progress_callback, "run_blind_inversion", "运行盲反演", indeterminate=True)
    inversion = run_weighted_integer_inversion(session.get("records", []), cfg)
    inversion["created_at"] = _now()
    session["inversion"] = inversion
    session["updated_at"] = _now()
    _write_json(session_path, session)
    _write_json(Path(init["session_root"]) / "normal_inversion.json", inversion)
    return {"session_root": init["session_root"], "inversion": inversion, "session": _public_session(session, init["session_root"])}


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
    start_frame = int(boundary["zero_v_start_frame"]) if "zero_v_start_frame" in boundary else int(round(float(boundary["zero_v_start_s"]) * fps))
    end_frame = int(boundary["zero_v_end_frame"]) if "zero_v_end_frame" in boundary else int(round(float(boundary["zero_v_end_s"]) * fps))
    start_frame = max(0, min(frame_count - 1, start_frame))
    end_frame = max(start_frame, min(frame_count - 1, end_frame))
    return {
        "zero_v_start_s": start_frame / fps,
        "zero_v_end_s": end_frame / fps,
        "zero_v_start_frame": start_frame,
        "zero_v_end_frame": end_frame,
        "source": str(boundary.get("source", "manual_ui")),
    }


def _selection_window(boundary: dict[str, Any], metadata: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    fps = float(metadata.get("fps") or 30.0)
    frame_count = int(metadata.get("frame_count") or 1)
    zero_start = int(boundary["zero_v_start_frame"])
    zero_end = int(boundary["zero_v_end_frame"])
    scfg = cfg.get("selection", {})
    before = float(scfg.get("before_zero_v_start_s", 1.0))
    after = float(scfg.get("after_zero_v_start_s", 0.5))
    start_frame = max(0, int(round(zero_start - before * fps)))
    end_frame = min(frame_count - 1, zero_end, int(round(zero_start + after * fps)))
    end_frame = max(start_frame, end_frame)
    return {
        "start_s": start_frame / fps,
        "end_s": end_frame / fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "source": "normal_v1_default",
    }


def _normalize_target(target: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    fps = float(metadata.get("fps") or 30.0)
    frame_count = int(metadata.get("frame_count") or 1)
    width = int(metadata.get("width") or 1)
    height = int(metadata.get("height") or 1)
    frame = int(target["target_frame"]) if "target_frame" in target else int(round(float(target["target_time_s"]) * fps))
    frame = max(0, min(frame_count - 1, frame))
    box = target.get("source_video_box") or {}
    x = max(0.0, min(float(width - 1), float(box.get("x", target.get("source_center", {}).get("x", 0.0)))))
    y = max(0.0, min(float(height - 1), float(box.get("y", target.get("source_center", {}).get("y", 0.0)))))
    w = max(1.0, min(float(width) - x, float(box.get("width", 1.0))))
    h = max(1.0, min(float(height) - y, float(box.get("height", 1.0))))
    center = target.get("source_center") or {"x": x + w / 2.0, "y": y + h / 2.0}
    return {
        **target,
        "target_frame": frame,
        "target_time_s": frame / fps,
        "source_center": {"x": float(center["x"]), "y": float(center["y"])},
        "source_video_box": {"x": x, "y": y, "width": w, "height": h},
    }


def _diagnostic_record(
    record_id: str,
    video_path: str,
    boundary: dict[str, Any],
    target: dict[str, Any],
    grid: dict[str, Any],
    flags: list[str],
    record_dir: Path,
    active: dict[str, Any],
    effective_cfg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_id": record_id,
        "retry_of_record_id": active.get("retry_of_record_id"),
        "created_at": _now(),
        "video_path": video_path,
        "video_sha256_16": file_sha256(video_path)[:16] if Path(video_path).exists() else "",
        "metadata": active.get("metadata"),
        "balance_voltage_V": active.get("balance_voltage_V"),
        "balance_confirmed": active.get("balance_confirmed"),
        "time_window": boundary,
        "target": target,
        "grid": grid,
        "parameter_overrides": active.get("parameter_overrides") or {},
        "effective_parameters": {"physics": effective_cfg["physics"], "grid": effective_cfg["grid"]},
        "crossing_events": [],
        "fit": {"valid": False, "flags": flags},
        "q": {"valid": False, "diagnostic_only": True, "flags": flags},
        "status": "diagnostic",
        "kept": False,
        "record_dir": str(record_dir),
        "recovery_suggestions": ["请先修正网格识别或有效测量区。"],
    }


def _restore_active_for_adjustment(session: dict[str, Any], record: dict[str, Any]) -> None:
    metadata = record.get("metadata") or {}
    session["active_video"] = {
        "state": "boundary_confirmed",
        "path": record.get("video_path"),
        "metadata": metadata,
        "video_url": file_url(record["video_path"]) if record.get("video_path") else "",
        "boundary_suggestion": record.get("time_window"),
        "boundary": record.get("time_window"),
        "grid": record.get("grid"),
        "adjustment_source_record_id": record.get("record_id"),
        "adjustment": {
            "record_id": record.get("record_id"),
            "target": record.get("target"),
            "balance_voltage_V": record.get("balance_voltage_V"),
            "balance_confirmed": record.get("balance_confirmed"),
            "parameter_overrides": record.get("parameter_overrides") or {},
        },
        "restored_for_adjustment_at": _now(),
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


def _public_session(session: dict[str, Any], session_root: str | None = None) -> dict[str, Any]:
    records = [_public_record(record) for record in session.get("records", [])]
    accepted = [record for record in records if record.get("status") == "accepted" and record.get("kept")]
    q_ready = [record for record in records if record.get("q_valid")]
    return {
        "schema_version": session.get("schema_version", 1),
        "session_id": session.get("session_id"),
        "session_root": session_root,
        "transient": bool(session.get("transient", True)),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "records": records,
        "counts": {"total": len(records), "q_ready": len(q_ready), "valid": len(accepted), "kept_valid": len(accepted), "selected_valid": len(accepted)},
        "eligible_for_inversion": len(accepted) >= 3,
        "inversion": session.get("inversion"),
        "active_video": session.get("active_video"),
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in record.items() if key not in {"record_dir"}}
    q = record.get("q") if isinstance(record.get("q"), dict) else {}
    fit = record.get("fit") if isinstance(record.get("fit"), dict) else {}
    tracking = record.get("tracking") if isinstance(record.get("tracking"), dict) else {}
    public.update(
        {
            "valid": record.get("status") == "accepted" and bool(record.get("kept")),
            "q_valid": bool(q.get("valid")),
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


def _require_active_state(session: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    active = session.get("active_video")
    if not isinstance(active, dict):
        raise RuntimeError("no active Normal video")
    state = str(active.get("state") or "")
    if state not in ACTIVE_VIDEO_STATES:
        if state in RECORD_STATES:
            raise RuntimeError(f"record status cannot be used as active_video.state: {state}")
        raise RuntimeError(f"unknown Normal active_video.state: {state}")
    if state not in allowed:
        raise RuntimeError(f"invalid Normal state transition: state={state}, expected={sorted(allowed)}")
    return active


def _find_record(session: dict[str, Any], record_id: str) -> dict[str, Any]:
    for record in session.get("records", []):
        if record.get("record_id") == record_id:
            return record
    raise RuntimeError(f"record not found: {record_id}")


def _find_crossing(record: dict[str, Any], event_id: str) -> dict[str, Any]:
    for event in record.get("crossing_events", []):
        if event.get("event_id") == event_id or event.get("id") == event_id:
            return event
    raise RuntimeError(f"crossing event not found: {event_id}")


def _all_crossings_reviewed_same(record: dict[str, Any]) -> bool:
    crossings = record.get("crossing_events") or []
    return all(event.get("review_result") == "same_drop" for event in crossings)


def _stage_emitter(callback: ProgressCallback | None) -> Callable[[str, str, int | None, int | None, str | None], None] | None:
    if callback is None:
        return None

    def emit(stage: str, label: str, current: int | None, total: int | None, unit: str | None) -> None:
        _emit(callback, stage, label, current=current, total=total, unit=unit)

    return emit


def _emit(callback: ProgressCallback | None, stage: str, label: str, current: int | None = None, total: int | None = None, unit: str | None = None, indeterminate: bool | None = None) -> None:
    if callback is None:
        return
    payload: dict[str, Any] = {"stage": stage, "label": label}
    if current is not None:
        payload["current"] = int(current)
    if total is not None:
        payload["total"] = int(total)
    if unit is not None:
        payload["unit"] = unit
    if indeterminate is not None:
        payload["indeterminate"] = bool(indeterminate)
    callback(payload)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
