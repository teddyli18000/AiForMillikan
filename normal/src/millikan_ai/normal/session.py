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

ProgressEventSink = Callable[[dict[str, Any]], None]


def initialize_session(session_root: str | None = None, run_root: str | None = None, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = normal_config(config_overrides)
    session_id = f"normal_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    root = Path(session_root) if session_root else Path(config["session"]["session_root"]) / session_id
    run = Path(run_root or config["session"]["run_root"])
    root.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    path = root / "normal_session.json"
    if session_root and path.exists():
        session = read_json_file(path)
    else:
        session = {
            "schema_version": 1,
            "session_id": session_id,
            "transient": True,
            "created_at": utc_timestamp(),
            "updated_at": utc_timestamp(),
            "records": [],
            "active_video": None,
            "inversion": None,
        }
        write_json_file(path, session)
    return {
        "session": public_session(session, str(root)),
        "session_file": str(path),
        "session_root": str(root),
        "run_root": str(run),
        "config": config,
    }


def inspect_video_only(video_path: str) -> dict[str, Any]:
    metadata = inspect_video(video_path)
    if not metadata.get("readable"):
        raise RuntimeError(f"无法读取视频：{video_path}")
    return {"video_path": video_path, "metadata": metadata, "video_url": file_url(video_path)}


def _prepared_video_state(
    video_path: str,
    metadata: dict[str, Any],
    suggestion: dict[str, Any],
    grid: dict[str, Any],
) -> dict[str, Any]:
    return {
        "state": "video_prepared",
        "path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary_suggestion": suggestion,
        "boundary": None,
        "grid": grid,
        "prepared_at": utc_timestamp(),
    }


def prepare_video(
    video_path: str,
    session_root: str | None = None,
    run_root: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    progress_callback: ProgressEventSink | None = None,
) -> dict[str, Any]:
    config = normal_config(config_overrides)
    opened = initialize_session(session_root, run_root, config_overrides)
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)

    emit_progress(progress_callback, "inspect_metadata", "读取视频元数据", indeterminate=True)
    metadata = inspect_video(video_path)
    if not metadata.get("readable"):
        raise RuntimeError(f"无法读取视频：{video_path}")

    boundary = suggest_zero_v_window(video_path, config, stage_progress_adapter(progress_callback))
    suggestion = boundary["suggestion"]
    emit_progress(progress_callback, "detect_visual_changes", "检测画面变化", indeterminate=True)
    emit_progress(progress_callback, "suggest_zero_v_window", "生成 0V 时间建议", indeterminate=True)
    grid = calibrate_grid(
        video_path,
        config,
        start_frame=int(suggestion.get("zero_v_start_frame", 0)),
        end_frame=int(suggestion.get("zero_v_end_frame", metadata["frame_count"] - 1)),
        progress_callback=stage_progress_adapter(progress_callback),
    )
    emit_progress(progress_callback, "detect_grid_lines", "识别网格线", indeterminate=True)

    session["active_video"] = _prepared_video_state(video_path, metadata, suggestion, grid)
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    emit_progress(progress_callback, "ready_for_boundary_review", "等待用户确认 0V 起止时间", indeterminate=True)
    return {
        "session_root": opened["session_root"],
        "video_path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary": suggestion,
        "boundary_diagnostics": {"samples": boundary.get("samples", []), "operations": boundary.get("operations", [])},
        "grid": grid,
        "session": public_session(session, opened["session_root"]),
        "config": config,
    }


def confirm_boundary(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = normal_config(config_overrides)
    opened = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    active = require_active_video(session, {"video_prepared", "boundary_confirmed"})
    metadata = active["metadata"]
    boundary = normalize_boundary_seconds(payload["boundary"], metadata)
    boundary["selection_window"] = build_selection_window(boundary, metadata, config)
    active["boundary"] = boundary
    active["state"] = "boundary_confirmed"
    active["boundary_confirmed_at"] = utc_timestamp()
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    return {"session_root": opened["session_root"], "active_video": active, "session": public_session(session, opened["session_root"])}


def select_target(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    opened = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    active = require_active_video(session, {"boundary_confirmed"})
    if not bool(payload.get("balance_confirmed")):
        raise RuntimeError("请先确认油滴在所填电压下处于平衡状态。")
    voltage = float(payload.get("balance_voltage_V", math.nan))
    if not math.isfinite(voltage) or voltage <= 0:
        raise RuntimeError("平衡电压必须为正数。")
    target = normalize_target_box(payload["target"], active["metadata"])
    boundary = active["boundary"]
    target_frame = int(target["target_frame"])
    window = boundary.get("selection_window") or build_selection_window(boundary, active["metadata"], normal_config(config_overrides))
    if not (int(window["start_frame"]) <= target_frame <= int(window["end_frame"])):
        raise RuntimeError("所选画面超出零电压起点附近的允许范围，请调整时间。")
    overrides = payload.get("parameter_overrides") or {}
    target["selection_window"] = window
    active["target"] = target
    active["retry_of_record_id"] = payload.get("retry_of_record_id")
    active["balance_voltage_V"] = voltage
    active["balance_confirmed"] = True
    active["parameter_overrides"] = overrides
    active["state"] = "target_selected"
    active["target_selected_at"] = utc_timestamp()
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    return {"session_root": opened["session_root"], "active_video": active, "session": public_session(session, opened["session_root"])}


def _measure_drop(
    request: TrackRequest,
    metadata: dict[str, Any],
    grid: dict[str, Any],
    balance_voltage_V: Any,
    effective_config: dict[str, Any],
    progress_callback: ProgressEventSink | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    tracking = run_tracking(request, progress_callback=stage_progress_adapter(progress_callback))
    emit_progress(progress_callback, "fit_velocity", "拟合 0V 下落速度", indeterminate=True)
    fit = fit_zero_v_velocity(tracking["track"], float(metadata.get("fps") or tracking["fps"] or 30.0), float(grid["scale_y_m_per_px"]), effective_config)
    emit_progress(progress_callback, "compute_q", "计算 q 和不确定度", indeterminate=True)
    q = compute_q(fit, float(balance_voltage_V), effective_config)
    q_ok = bool(q.get("valid") and fit.get("valid"))
    crossings = tracking["crossing_events"]
    if not q_ok:
        status = "diagnostic"
    elif crossings:
        status = "pending_crossing_review"
    else:
        status = "pending_user_confirmation"
    return tracking, fit, q, crossings, status


def save_measurement(payload: dict[str, Any], config_overrides: dict[str, Any] | None = None, progress_callback: ProgressEventSink | None = None) -> dict[str, Any]:
    opened = initialize_session(payload.get("session_root"), payload.get("run_root"), config_overrides)
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    active = require_active_video(session, {"target_selected"})
    active["state"] = "tracking"
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)

    record_id = f"rec_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    record_dir = Path(opened["session_root"]) / "records" / record_id
    record_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(active["path"])
    metadata = active["metadata"]
    boundary = active["boundary"]
    grid = active["grid"]
    target = active["target"]
    overrides = active.get("parameter_overrides") or {}
    effective_config = normal_config(overrides)

    emit_progress(progress_callback, "validate_measurement_inputs", "校验测量输入", indeterminate=True)
    if not grid.get("valid"):
        record = build_diagnostic_record(record_id, video_path, boundary, target, grid, ["grid_calibration_invalid"], record_dir, active, effective_config)
    else:
        tracking, fit, q, crossings, status = _measure_drop(
            TrackRequest(
                video_path=video_path,
                target_frame=int(target["target_frame"]),
                zero_v_start_frame=int(boundary["zero_v_start_frame"]),
                zero_v_end_frame=int(boundary["zero_v_end_frame"]),
                source_center=(float(target["source_center"]["x"]), float(target["source_center"]["y"])),
                grid=grid,
                run_dir=str(record_dir),
                config=effective_config,
            ),
            metadata,
            grid,
            active["balance_voltage_V"],
            effective_config,
            progress_callback,
        )
        record = {
            "schema_version": 1,
            "record_id": record_id,
            "retry_of_record_id": active.get("retry_of_record_id"),
            "created_at": utc_timestamp(),
            "video_path": video_path,
            "video_sha256_16": file_sha256(video_path)[:16] if Path(video_path).exists() else "",
            "metadata": metadata,
            "balance_voltage_V": float(active["balance_voltage_V"]),
            "balance_confirmed": True,
            "time_window": boundary,
            "target": target,
            "grid": grid,
            "parameter_overrides": overrides,
            "effective_parameters": {"physics": effective_config["physics"], "grid": effective_config["grid"]},
            "tracking": {"stats": track_point_counts(tracking["track"]), "artifacts": tracking_artifact_paths(tracking), "track": tracking["track"], "track_review_frames": tracking.get("track_review_frames") or []},
            "crossing_events": crossings,
            "fit": fit,
            "q": q,
            "status": status,
            "kept": False,
            "record_dir": str(record_dir),
            "recovery_suggestions": q.get("recovery_suggestions") or fit.get("recovery_suggestions") or [],
        }
        write_json_file(record_dir / "q_result.json", q)

    write_json_file(record_dir / "record_manifest.json", record)
    session.setdefault("records", []).append(record)
    active["last_record_id"] = record_id
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    return {"session_root": opened["session_root"], "record": public_record(record), "session": public_session(session, opened["session_root"])}


def prepare_crossing_review(payload: dict[str, Any]) -> dict[str, Any]:
    opened = initialize_session(payload.get("session_root"))
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    record = find_record_or_raise(session, str(payload["record_id"]))
    event = find_crossing_or_raise(record, str(payload["event_id"]))
    record_dir = Path(record["record_dir"])
    clip = record_dir / "crossing_reviews" / f"{event['event_id']}.mp4"
    frames_manifest = clip.parent / f"{event['event_id']}_frames" / "frames_manifest.json"
    if not clip.exists() or not frames_manifest.exists():
        review = make_crossing_review_clip(record["video_path"], event, clip, (record.get("tracking") or {}).get("track") or [])
        event["review_clip_path"] = review["clip_path"]
        event["review_clip_url"] = file_url(review["clip_path"])
        event["review_source_video_box"] = review["source_video_box"]
        event["review_clip_start_time_s"] = review["start_time_s"]
        event["review_clip_end_time_s"] = review["end_time_s"]
        event["review_frames_manifest_path"] = review["frames_manifest_path"]
        event["review_frames"] = review_frames_with_image_urls(review["review_frames"])
    else:
        event["review_clip_path"] = str(clip)
        event["review_clip_url"] = file_url(clip)
        frames = read_json_file(frames_manifest)
        event["review_frames_manifest_path"] = str(frames_manifest)
        event["review_frames"] = review_frames_with_image_urls(frames)
        if not event["review_frames"]:
            raise RuntimeError(f"未能生成身份复核画面：{frames_manifest}")
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    write_json_file(record_dir / "record_manifest.json", record)
    return {"session_root": opened["session_root"], "record": public_record(record), "event": event, "session": public_session(session, opened["session_root"])}


def review_frames_with_image_urls(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frames_with_urls: list[dict[str, Any]] = []
    for frame in frames:
        image_path = frame.get("image_path")
        if not image_path:
            continue
        frame_copy = dict(frame)
        frame_copy["image_url"] = file_url(image_path)
        frames_with_urls.append(frame_copy)
    return frames_with_urls


def review_crossing(payload: dict[str, Any]) -> dict[str, Any]:
    result = str(payload.get("result") or "")
    if result not in {"same_drop", "different_drop"}:
        raise RuntimeError("请选择身份复核结果。")
    opened = initialize_session(payload.get("session_root"))
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    record = find_record_or_raise(session, str(payload["record_id"]))
    event = find_crossing_or_raise(record, str(payload["event_id"]))
    event["review_result"] = result
    event["reviewed_at"] = utc_timestamp()
    if result == "different_drop":
        record["status"] = "rejected_crossing_identity"
        record["kept"] = False
        session["inversion"] = None
        reopen_video_for_adjustment(session, record)
    elif record.get("status") == "pending_crossing_review" and crossings_all_confirmed_same(record):
        record["status"] = "pending_user_confirmation"
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    write_json_file(Path(record["record_dir"]) / "record_manifest.json", record)
    return {"session_root": opened["session_root"], "record": public_record(record), "session": public_session(session, opened["session_root"])}


def update_record_selection(session_root: str | None, record_id: str, kept: bool) -> dict[str, Any]:
    opened = initialize_session(session_root)
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    record = find_record_or_raise(session, record_id)
    if kept:
        if record.get("status") == "accepted":
            record["kept"] = True
        elif record.get("status") == "pending_user_confirmation" and crossings_all_confirmed_same(record) and bool((record.get("q") or {}).get("valid")):
            record["status"] = "accepted"
            record["kept"] = True
            record["accepted_at"] = utc_timestamp()
        else:
            raise RuntimeError("当前测量尚未完成复核，不能保留。")
    else:
        record["status"] = "rejected_by_user"
        record["kept"] = False
        reopen_video_for_adjustment(session, record)
    session["inversion"] = None
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    write_json_file(Path(record["record_dir"]) / "record_manifest.json", record)
    return {"session": public_session(session, opened["session_root"])}


def _next_droplet_video_state(
    video_path: str,
    metadata: dict[str, Any],
    boundary: dict[str, Any],
    grid: dict[str, Any],
    record: dict[str, Any] | None,
    active: dict[str, Any],
) -> dict[str, Any]:
    # 优先沿用上一条记录的电压和参数，active_video 里没有才退回当前会话。
    return {
        "state": "boundary_confirmed",
        "path": video_path,
        "metadata": metadata,
        "video_url": file_url(video_path),
        "boundary_suggestion": boundary,
        "boundary": boundary,
        "grid": grid,
        "previous_balance_voltage_V": (record or {}).get("balance_voltage_V") or active.get("balance_voltage_V"),
        "previous_parameter_overrides": (record or {}).get("parameter_overrides") or active.get("parameter_overrides") or {},
        "next_droplet_from_record_id": (record or {}).get("record_id"),
        "next_droplet_started_at": utc_timestamp(),
    }


def start_next_droplet(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "")
    if mode not in {"same_video", "different_video"}:
        raise RuntimeError("请选择继续使用当前视频或更换视频。")
    opened = initialize_session(payload.get("session_root"))
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    if mode == "different_video":
        session["active_video"] = None
        session["updated_at"] = utc_timestamp()
        write_json_file(session_path, session)
        return {"session_root": opened["session_root"], "active_video": None, "session": public_session(session, opened["session_root"])}

    record = None
    record_id = payload.get("record_id")
    if record_id:
        record = find_record_or_raise(session, str(record_id))
    active = session.get("active_video") if isinstance(session.get("active_video"), dict) else {}
    video_path = (record or {}).get("video_path") or active.get("path")
    metadata = (record or {}).get("metadata") or active.get("metadata")
    boundary = (record or {}).get("time_window") or active.get("boundary")
    grid = (record or {}).get("grid") or active.get("grid")
    if not video_path or not isinstance(metadata, dict) or not isinstance(boundary, dict) or not isinstance(grid, dict):
        raise RuntimeError("当前没有可继续测量的视频，请重新导入视频。")
    session["active_video"] = _next_droplet_video_state(video_path, metadata, boundary, grid, record, active)
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    return {"session_root": opened["session_root"], "active_video": session["active_video"], "session": public_session(session, opened["session_root"])}


def run_inversion(session_root: str | None = None, config_overrides: dict[str, Any] | None = None, progress_callback: ProgressEventSink | None = None) -> dict[str, Any]:
    config = normal_config(config_overrides)
    opened = initialize_session(session_root, config_overrides=config_overrides)
    session_path = Path(opened["session_file"])
    session = read_json_file(session_path)
    emit_progress(progress_callback, "run_blind_inversion", "运行盲反演", indeterminate=True)
    inversion = run_weighted_integer_inversion(session.get("records", []), config)
    inversion["created_at"] = utc_timestamp()
    session["inversion"] = inversion
    session["updated_at"] = utc_timestamp()
    write_json_file(session_path, session)
    write_json_file(Path(opened["session_root"]) / "normal_inversion.json", inversion)
    return {"session_root": opened["session_root"], "inversion": inversion, "session": public_session(session, opened["session_root"])}


def export_session(session_root: str | None, export_root: str) -> dict[str, Any]:
    opened = initialize_session(session_root)
    source = Path(opened["session_root"])
    session = read_json_file(Path(opened["session_file"]))
    destination = Path(export_root) / f"{session['session_id']}_export"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if (source / "records").exists():
        shutil.copytree(source / "records", destination / "records")
    write_json_file(destination / "normal_session.json", session)
    if session.get("inversion"):
        write_json_file(destination / "normal_inversion.json", session["inversion"])
    report = destination / "normal_session_report.md"
    report.write_text(render_report(session), encoding="utf-8")
    manifest = {"schema_version": 1, "session_id": session["session_id"], "exported_at": utc_timestamp(), "files": sorted(str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file())}
    write_json_file(destination / "export_manifest.json", manifest)
    return {"destination": str(destination), "manifest": manifest, "markdown": str(report)}


def render_report(session: dict[str, Any]) -> str:
    lines = ["# 密立根油滴实验记录", "", "| 测量序号 | 结果 | 电荷 q | 不确定度 σq | 视频 |", "| ---: | --- | ---: | ---: | --- |"]
    records = session.get("records", [])
    lines.extend(_measurement_report_rows(records))
    if records:
        lines.extend(["", "σq 由速度拟合误差传播计算，未计仪器和物性参数误差。"])
    inversion = session.get("inversion")
    if inversion:
        lines.extend(_inversion_report_lines(inversion))
    return "\n".join(lines) + "\n"


def _measurement_report_rows(records: list[dict[str, Any]]) -> list[str]:
    # 报表只给人看，内部 id 和机器字段一律不带出来。
    labels = {
        "pending_crossing_review": "待复核",
        "pending_user_confirmation": "待确认",
        "accepted": "已保留",
        "diagnostic": "仅供诊断",
        "rejected_crossing_identity": "身份复核未通过",
        "rejected_by_user": "已排除",
    }
    rows = []
    for index, record in enumerate(records, start=1):
        charge = record.get("q", {})
        video_name = Path(str(record.get("video_path", ""))).name
        rows.append(f"| {index} | {labels.get(record.get('status'), '待确认')} | {format_charge_si(charge.get('q_C'))} | {format_charge_si(charge.get('sigma_q_C'))} | {video_name} |")
    return rows


def _inversion_report_lines(inversion: dict[str, Any]) -> list[str]:
    comparison = inversion.get("reference_comparison") or {}
    result_labels = {
        "reliable": "可靠候选",
        "exploratory": "样本较少",
        "diagnostic": "需复核",
        "insufficient_eligible_records": "记录不足",
    }
    flag_labels = {
        "insufficient_eligible_records": "可用测量记录不足",
        "weighted_residual_too_large": "电荷与整数倍的偏差较大",
        "integer_assignments_nonprimitive": "整数分配存在公因数",
        "search_boundary_hit": "估计值触及搜索范围边界",
        "integer_assignment_not_stable": "整数分配尚未稳定",
        "exploratory_small_sample": "样本较少，结果仅供参考",
    }
    lines = [
        "",
        "## 元电荷结果",
        "",
        f"- 结果状态：{result_labels.get(inversion.get('status'), '未估计')}",
        f"- 估计值：{format_charge_si(inversion.get('e_hat_C'))}",
        f"- 标准不确定度：{format_charge_si(inversion.get('sigma_e_C'))}",
        f"- 相对不确定度：{format_percent(comparison.get('relative_uncertainty_percent'))}",
        f"- 参与测量：{inversion.get('valid_q_count', '-')} 次",
    ]
    lines.extend(f"- 诊断：{flag_labels.get(flag, flag)}" for flag in inversion.get("flags", []))
    percent_error = comparison.get("percent_error_vs_reference")
    if percent_error is not None:
        reference = format_charge_si(comparison.get("reference_e_C"))
        lines.append(f"- 与标准值的相对误差：{format_percent(percent_error)}（标准值 {reference}）")
    return lines


def format_charge_si(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "-"
    return f"{number / 1e-19:.5g} × 10⁻¹⁹ C"


def format_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.3g}%" if math.isfinite(number) else "-"


def normalize_boundary_seconds(boundary: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    fps = float(metadata.get("fps") or 30.0)
    frame_count = int(metadata.get("frame_count") or 1)
    if "zero_v_start_s" in boundary:
        start_frame = int(round(float(boundary["zero_v_start_s"]) * fps))
    else:
        start_frame = int(boundary["zero_v_start_frame"])
    if "zero_v_end_s" in boundary:
        end_frame = int(round(float(boundary["zero_v_end_s"]) * fps))
    else:
        end_frame = int(boundary["zero_v_end_frame"])
    start_frame = max(0, min(frame_count - 1, start_frame))
    end_frame = max(start_frame, min(frame_count - 1, end_frame))
    return {
        "zero_v_start_s": start_frame / fps,
        "zero_v_end_s": end_frame / fps,
        "zero_v_start_frame": start_frame,
        "zero_v_end_frame": end_frame,
        "source": str(boundary.get("source", "manual_ui")),
    }


def build_selection_window(boundary: dict[str, Any], metadata: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    fps = float(metadata.get("fps") or 30.0)
    frame_count = int(metadata.get("frame_count") or 1)
    zero_start = int(boundary["zero_v_start_frame"])
    selection_config = config.get("selection", {})
    before = float(selection_config.get("before_zero_v_start_s", 0.5))
    after = float(selection_config.get("after_zero_v_start_s", 0.5))
    start_frame = max(0, int(round(zero_start - before * fps)))
    end_frame = min(frame_count - 1, int(round(zero_start + after * fps)))
    end_frame = max(start_frame, end_frame)
    return {
        "start_s": start_frame / fps,
        "end_s": end_frame / fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "source": "normal_v1_default",
    }


def normalize_target_box(target: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
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


def build_diagnostic_record(
    record_id: str,
    video_path: str,
    boundary: dict[str, Any],
    target: dict[str, Any],
    grid: dict[str, Any],
    flags: list[str],
    record_dir: Path,
    active: dict[str, Any],
    effective_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_id": record_id,
        "retry_of_record_id": active.get("retry_of_record_id"),
        "created_at": utc_timestamp(),
        "video_path": video_path,
        "video_sha256_16": file_sha256(video_path)[:16] if Path(video_path).exists() else "",
        "metadata": active.get("metadata"),
        "balance_voltage_V": active.get("balance_voltage_V"),
        "balance_confirmed": active.get("balance_confirmed"),
        "time_window": boundary,
        "target": target,
        "grid": grid,
        "parameter_overrides": active.get("parameter_overrides") or {},
        "effective_parameters": {"physics": effective_config["physics"], "grid": effective_config["grid"]},
        "crossing_events": [],
        "fit": {"valid": False, "flags": flags},
        "q": {"valid": False, "diagnostic_only": True, "flags": flags},
        "status": "diagnostic",
        "kept": False,
        "record_dir": str(record_dir),
        "recovery_suggestions": ["请先修正网格识别或有效测量区。"],
    }


def reopen_video_for_adjustment(session: dict[str, Any], record: dict[str, Any]) -> None:
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
        "restored_for_adjustment_at": utc_timestamp(),
    }


def track_point_counts(track: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_points": len(track),
        "detected_points": sum(1 for row in track if row.get("detected")),
        "missing_points": sum(1 for row in track if row.get("state") == "missing"),
        "reacquired_points": sum(1 for row in track if row.get("state") == "reacquired"),
    }


def tracking_artifact_paths(tracking: dict[str, Any]) -> dict[str, str]:
    return {key: value for key, value in tracking.items() if key.endswith("_csv") or key.endswith("_json") or key.endswith("_mp4")}


def public_session(session: dict[str, Any], session_root: str | None = None) -> dict[str, Any]:
    records = [public_record(record) for record in session.get("records", [])]
    accepted = [record for record in records if record.get("status") == "accepted" and record.get("kept")]
    return {
        "schema_version": session.get("schema_version", 1),
        "session_id": session.get("session_id"),
        "session_root": session_root,
        "transient": bool(session.get("transient", True)),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "records": records,
        "counts": {"total": len(records), "kept_valid": len(accepted)},
        "eligible_for_inversion": len(accepted) >= 3,
        "inversion": session.get("inversion"),
        "active_video": session.get("active_video"),
    }


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in record.items() if key not in {"record_dir"}}
    q = record.get("q") if isinstance(record.get("q"), dict) else {}
    fit = record.get("fit") if isinstance(record.get("fit"), dict) else {}
    tracking = record.get("tracking") if isinstance(record.get("tracking"), dict) else {}
    artifacts = tracking.get("artifacts") or {}
    artifact_urls = {key: file_url(value) for key, value in artifacts.items() if key.endswith("_mp4") and value}
    public.update(
        {
            "valid": record.get("status") == "accepted" and bool(record.get("kept")),
            "q_valid": bool(q.get("valid")),
            "q_C": q.get("q_C"),
            "charge_abs_C": q.get("charge_abs_C"),
            "sigma_q_C": q.get("sigma_q_C"),
            "radius_m": q.get("radius_m"),
            "fall_velocity_m_s": fit.get("velocity_m_s"),
            "artifact_urls": artifact_urls,
            "track_review_frames": review_frames_with_image_urls(tracking.get("track_review_frames") or []),
            "crossings": record.get("crossing_events") or [],
        }
    )
    return public


def require_active_video(session: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    active = session.get("active_video")
    if not isinstance(active, dict):
        raise RuntimeError("当前没有可操作的视频，请先导入并处理视频。")
    state = str(active.get("state") or "")
    if state not in ACTIVE_VIDEO_STATES:
        if state in RECORD_STATES:
            raise RuntimeError("测量状态不适用于当前操作，请返回测量流程继续。")
        raise RuntimeError("测量状态无效，请重新导入视频。")
    if state not in allowed:
        raise RuntimeError("当前步骤无法执行该操作，请按测量流程继续。")
    return active


def find_record_or_raise(session: dict[str, Any], record_id: str) -> dict[str, Any]:
    for record in session.get("records", []):
        if record.get("record_id") == record_id:
            return record
    raise RuntimeError(f"未找到这条测量记录：{record_id}")


def find_crossing_or_raise(record: dict[str, Any], event_id: str) -> dict[str, Any]:
    for event in record.get("crossing_events", []):
        if event.get("event_id") == event_id:
            return event
    raise RuntimeError(f"未找到这段轨迹复核记录：{event_id}")


def crossings_all_confirmed_same(record: dict[str, Any]) -> bool:
    crossings = record.get("crossing_events") or []
    return all(event.get("review_result") == "same_drop" for event in crossings)


def stage_progress_adapter(callback: ProgressEventSink | None) -> Callable[[str, str, int | None, int | None, str | None], None] | None:
    if callback is None:
        return None

    def emit(stage: str, label: str, current: int | None, total: int | None, unit: str | None) -> None:
        emit_progress(callback, stage, label, current=current, total=total, unit=unit)

    return emit


def emit_progress(callback: ProgressEventSink | None, stage: str, label: str, current: int | None = None, total: int | None = None, unit: str | None = None, indeterminate: bool | None = None) -> None:
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


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
