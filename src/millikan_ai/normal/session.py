from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import normal_config
from .grid import calibrate_grid
from .inversion import run_experimental_adapter, run_weighted_integer_inversion
from .physics import compute_q_with_uncertainty
from .tracking import TrackRequest, run_tracking
from .video import file_sha256, inspect_video
from .voltage import suggest_balance_fall_boundaries


def initialize_session(session_root: str, run_root: str, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(session_root)
    root.mkdir(parents=True, exist_ok=True)
    run = Path(run_root)
    run.mkdir(parents=True, exist_ok=True)
    session_path = root / "normal_session.json"
    if session_path.exists():
        session = _read_json(session_path)
    else:
        session = {
            "schema_version": 1,
            "session_id": f"normal_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            "created_at": _now(),
            "updated_at": _now(),
            "records": [],
            "active_video": None,
        }
        _write_json(session_path, session)
    return {
        "session": _public_session(session),
        "session_file": str(session_path),
        "config": normal_config(config_overrides),
    }


def prepare_video(video_path: str, session_root: str, run_root: str, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    metadata = inspect_video(video_path)
    suggestion = suggest_balance_fall_boundaries(video_path, cfg)
    grid = calibrate_grid(
        video_path,
        cfg,
        start_frame=int(suggestion["suggestion"].get("selection_frame", 0)),
        end_frame=int(suggestion["suggestion"].get("fall_end_frame", metadata.get("frame_count", 1) - 1)),
    )
    session_path = Path(session_root) / "normal_session.json"
    session = _ensure_session(session_root, run_root)
    session["active_video"] = {
        "path": video_path,
        "metadata": metadata,
        "suggestion": suggestion["suggestion"],
        "grid": grid,
        "prepared_at": _now(),
    }
    session["updated_at"] = _now()
    _write_json(session_path, session)
    return {"metadata": metadata, "boundary": suggestion, "grid": grid, "session": _public_session(session)}


def save_measurement(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normal_config(config_overrides)
    session_root = str(payload["session_root"])
    run_root = str(payload["run_root"])
    session = _ensure_session(session_root, run_root)
    record_id = f"rec_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    record_dir = Path(session_root) / "records" / record_id
    record_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(payload["video_path"])
    boundary = payload["boundary"]
    target = payload["target"]
    grid = payload["grid"]
    if not grid.get("valid"):
        record = _diagnostic_record(record_id, session["session_id"], video_path, record_dir, payload, ["grid_calibration_invalid"], ["请先修正第二条和倒数第二条水平网格线。"])
    else:
        tracking = run_tracking(TrackRequest(
            video_path=video_path,
            target_frame=int(target["target_frame"]),
            fall_start_frame=int(boundary["fall_start_frame"]),
            fall_end_frame=int(boundary["fall_end_frame"]),
            source_center=(float(target["source_center"]["x"]), float(target["source_center"]["y"])),
            source_video_box=target["source_video_box"],
            grid=grid,
            run_dir=str(record_dir),
            config=cfg,
        ))
        fit = tracking["fit"]
        if payload.get("balance_verified") is False:
            fit.setdefault("flags", []).append("balance_state_not_fully_verified")
            fit.setdefault("recovery_suggestions", []).append("如果可能，请在电压切换前更早的平衡帧重新框选。")
        q = compute_q_with_uncertainty(fit, float(payload["balance_voltage_V"]), float(grid["scale_y_m_per_px"]), cfg)
        status = "valid" if q.get("valid") and not q.get("diagnostic_only") else "diagnostic"
        record = {
            "schema_version": 1,
            "record_id": record_id,
            "session_id": session["session_id"],
            "created_at": _now(),
            "video_path": video_path,
            "video_sha256_16": file_sha256(Path(video_path))[:16] if Path(video_path).exists() else "",
            "balance_voltage_V": float(payload["balance_voltage_V"]),
            "target": target,
            "boundary": boundary,
            "grid": grid,
            "tracking_stats": _tracking_stats(tracking["track"]),
            "track": tracking["track"],
            "crossing_events": tracking["crossing_events"],
            "fit": fit,
            "q": q,
            "status": status,
            "selected": status == "valid",
            "record_dir": str(record_dir),
            "artifacts": {key: value for key, value in tracking.items() if key.endswith("_json") or key.endswith("_csv") or key.endswith("_mp4")},
            "recovery_suggestions": q.get("recovery_suggestions") or fit.get("recovery_suggestions") or [],
        }
        _write_record_artifacts(record_dir, record)
    session["records"].append(record)
    session["updated_at"] = _now()
    _write_json(Path(session_root) / "normal_session.json", session)
    return {"record": _public_record(record), "session": _public_session(session)}


def update_record_selection(session_root: str, record_id: str, selected: bool) -> dict[str, Any]:
    session = _read_json(Path(session_root) / "normal_session.json")
    for record in session.get("records", []):
        if record.get("record_id") == record_id:
            record["selected"] = bool(selected) and record.get("status") == "valid"
            break
    session["updated_at"] = _now()
    _write_json(Path(session_root) / "normal_session.json", session)
    return {"session": _public_session(session)}


def run_inversion(session_root: str, config: dict[str, Any]) -> dict[str, Any]:
    session = _read_json(Path(session_root) / "normal_session.json")
    records = session.get("records", [])
    normal = run_weighted_integer_inversion(records, normal_config())
    experimental = run_experimental_adapter(records, config)
    result = {"normal": normal, "experimental": experimental, "created_at": _now()}
    _write_json(Path(session_root) / "inversion_result.json", result)
    session["inversion"] = result
    session["updated_at"] = _now()
    _write_json(Path(session_root) / "normal_session.json", session)
    return {"inversion": result, "session": _public_session(session)}


def export_session(session_root: str, export_root: str) -> dict[str, Any]:
    source = Path(session_root)
    session = _read_json(source / "normal_session.json")
    destination = Path(export_root) / f"{session['session_id']}_export"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    records_dir = destination / "records"
    records_dir.mkdir()
    for record in session.get("records", []):
        record_dir = Path(record.get("record_dir", ""))
        if record_dir.exists():
            shutil.copytree(record_dir, records_dir / record["record_id"])
    report_md = destination / "normal_session_report.md"
    report_md.write_text(render_markdown_report(session), encoding="utf-8")
    _write_json(destination / "normal_session.json", session)
    manifest = {
        "schema_version": 1,
        "session_id": session["session_id"],
        "exported_at": _now(),
        "files": sorted(str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()),
    }
    _write_json(destination / "export_manifest.json", manifest)
    return {"destination": str(destination), "manifest": manifest, "markdown": str(report_md)}


def create_qa_fixture_session(session_root: str, run_root: str) -> dict[str, Any]:
    session = _ensure_session(session_root, run_root)
    for idx, n in enumerate([4, 5, 6], start=1):
        record_id = f"qa_fixture_{idx:03d}"
        q = 1.602176634e-19 * n
        record = {
            "schema_version": 1,
            "record_id": record_id,
            "session_id": session["session_id"],
            "created_at": _now(),
            "video_path": "QA fixture session",
            "balance_voltage_V": 240.0,
            "target": {},
            "boundary": {},
            "grid": {},
            "tracking_stats": {},
            "crossing_events": [],
            "fit": {"valid": True, "r2": 0.99},
            "q": {"valid": True, "diagnostic_only": False, "charge_abs_C": q, "sigma_q_total_C": q * 0.03},
            "status": "valid",
            "selected": True,
            "record_dir": str(Path(session_root) / "records" / record_id),
            "qa_fixture": True,
            "recovery_suggestions": [],
        }
        Path(record["record_dir"]).mkdir(parents=True, exist_ok=True)
        _write_record_artifacts(Path(record["record_dir"]), record)
        session["records"].append(record)
    session["updated_at"] = _now()
    session["qa_fixture"] = True
    _write_json(Path(session_root) / "normal_session.json", session)
    return {"session": _public_session(session)}


def render_markdown_report(session: dict[str, Any]) -> str:
    valid_selected = [row for row in session.get("records", []) if row.get("selected") and row.get("status") == "valid"]
    lines = [
        "# Millikan AI Normal Mode Session Report",
        "",
        f"Session: `{session.get('session_id')}`",
        f"Generated: {_now()}",
        "",
        "## Records",
        "",
        "| Record | Status | Selected | q (C) | sigma_q (C) | Notes |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for record in session.get("records", []):
        q = record.get("q", {})
        flags = ", ".join(q.get("flags", []) or record.get("fit", {}).get("flags", []) or [])
        lines.append(f"| {record.get('record_id')} | {record.get('status')} | {record.get('selected')} | {q.get('charge_abs_C', '-')} | {q.get('sigma_q_total_C', '-')} | {flags or '-'} |")
    if len(valid_selected) >= 3 and session.get("inversion"):
        lines.extend(["", "## Blind Inversion", "", "```json", json.dumps(session["inversion"], ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "## Limitations", "", "Diagnostic records are retained for review but are not used for blind inversion."])
    return "\n".join(lines) + "\n"


def _ensure_session(session_root: str, run_root: str) -> dict[str, Any]:
    result = initialize_session(session_root, run_root)
    return _read_json(Path(result["session_file"]))


def _diagnostic_record(record_id: str, session_id: str, video_path: str, record_dir: Path, payload: dict[str, Any], flags: list[str], suggestions: list[str]) -> dict[str, Any]:
    record = {
        "schema_version": 1,
        "record_id": record_id,
        "session_id": session_id,
        "created_at": _now(),
        "video_path": video_path,
        "balance_voltage_V": float(payload.get("balance_voltage_V", 0.0)),
        "target": payload.get("target", {}),
        "boundary": payload.get("boundary", {}),
        "grid": payload.get("grid", {}),
        "tracking_stats": {},
        "crossing_events": [],
        "fit": {"valid": False, "flags": flags},
        "q": {"valid": False, "diagnostic_only": True, "flags": flags, "recovery_suggestions": suggestions},
        "status": "diagnostic",
        "selected": False,
        "record_dir": str(record_dir),
        "recovery_suggestions": suggestions,
    }
    _write_record_artifacts(record_dir, record)
    return record


def _write_record_artifacts(record_dir: Path, record: dict[str, Any]) -> None:
    _write_json(record_dir / "record_manifest.json", record)
    (record_dir / "single_measurement_report.md").write_text(render_markdown_report({"session_id": record["session_id"], "records": [record]}), encoding="utf-8")


def _tracking_stats(track: list[dict[str, Any]]) -> dict[str, int]:
    states = [row.get("state") for row in track]
    return {
        "tracking_points": sum(1 for state in states if state == "tracking"),
        "missing_points": sum(1 for state in states if state == "missing"),
        "reacquired_points": sum(1 for state in states if state == "reacquired"),
        "total_points": len(states),
    }


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    records = [_public_record(row) for row in session.get("records", [])]
    valid = [row for row in records if row.get("status") == "valid"]
    selected = [row for row in valid if row.get("selected")]
    return {
        "schema_version": session.get("schema_version", 1),
        "session_id": session.get("session_id"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "records": records,
        "counts": {"total": len(records), "valid": len(valid), "selected_valid": len(selected)},
        "eligible_for_inversion": len(selected) >= 3,
        "qa_fixture": bool(session.get("qa_fixture", False)),
        "inversion": session.get("inversion"),
        "active_video": session.get("active_video"),
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"record_dir"}}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
