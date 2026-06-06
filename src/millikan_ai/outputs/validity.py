from __future__ import annotations

from typing import Any

import pandas as pd


def _check(check_id: str, passed: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, object]:
    return {"id": check_id, "passed": bool(passed), "message": message, "details": details or {}}


def build_validity_report(
    diagnostics: dict[str, Any],
    drop_result: dict[str, Any],
    elementary: dict[str, Any],
    platforms: pd.DataFrame,
    segments: pd.DataFrame,
    candidates: pd.DataFrame,
) -> dict[str, object]:
    video = diagnostics.get("video", {})
    grid = diagnostics.get("grid", {})
    top_candidate = candidates.head(1).to_dict("records")[0] if not candidates.empty else {}
    distinct_voltages = int(platforms["voltage_V"].dropna().nunique()) if "voltage_V" in platforms else 0
    stable_segments = int(segments["stable"].astype(bool).sum()) if "stable" in segments and not segments.empty else 0
    candidate_reject_reason = str(top_candidate.get("reject_reason", "") or "")
    checks = [
        _check("video_readable", bool(video.get("readable")), "Video can be opened by OpenCV.", {"path": video.get("path")}),
        _check("fps_valid", float(video.get("fps") or 0) > 0, "FPS is available for frame-to-time conversion.", {"fps": video.get("fps")}),
        _check(
            "scale_calibrated",
            bool(grid.get("scale_y_m_per_px")),
            "Grid distance calibration produced scale_y_m_per_px.",
            {"scale_y_m_per_px": grid.get("scale_y_m_per_px"), "warnings": grid.get("warnings", [])},
        ),
        _check(
            "enough_voltage_platforms",
            int(diagnostics.get("platform_count", 0)) >= 2,
            "At least two voltage platforms are required for q calculation.",
            {"platform_count": diagnostics.get("platform_count", 0)},
        ),
        _check(
            "distinct_voltage_values",
            distinct_voltages >= 2,
            "At least two distinct voltage values are required.",
            {"distinct_voltage_count": distinct_voltages},
        ),
        _check(
            "best_track_present",
            int(diagnostics.get("track_rows", 0)) > 0,
            "A best droplet track was produced.",
            {"track_rows": diagnostics.get("track_rows", 0)},
        ),
        _check(
            "candidate_not_rejected",
            candidate_reject_reason == "",
            "Best candidate has no hard-rule reject reason.",
            {"candidate_id": top_candidate.get("candidate_id"), "reject_reason": candidate_reject_reason},
        ),
        _check(
            "stable_segments_present",
            stable_segments >= 2,
            "At least two stable fitted velocity segments are required.",
            {"stable_segment_count": stable_segments},
        ),
        _check("drop_q_valid", bool(drop_result.get("valid")), "Physics q calculation is valid.", {"flags": drop_result.get("flags", [])}),
        _check(
            "elementary_charge_status",
            bool(elementary.get("valid")) or "insufficient_independent_drops" in elementary.get("flags", []) or "insufficient_drops" in elementary.get("flags", []),
            "Elementary-charge estimation either succeeded or reported an explicit insufficiency reason.",
            {"flags": elementary.get("flags", []), "valid": elementary.get("valid")},
        ),
    ]
    blocking_failed = [check["id"] for check in checks if not check["passed"] and check["id"] != "elementary_charge_status"]
    return {
        "schema_version": 1,
        "overall_valid_for_q": bool(drop_result.get("valid")) and not blocking_failed,
        "blocking_failed_checks": blocking_failed,
        "checks": checks,
        "combined_flags": list(diagnostics.get("flags", [])) + list(drop_result.get("flags", [])) + list(elementary.get("flags", [])),
    }
