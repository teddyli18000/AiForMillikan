from __future__ import annotations

from collections import Counter

import pandas as pd


def _bounded(value: object, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _trajectory_score(row: dict[str, object], config: dict) -> tuple[float, list[str]]:
    quality_cfg = config["quality"]
    thresholds = quality_cfg["thresholds"]
    missing_ratio = float(row.get("missing_ratio", 1.0) or 0.0)
    duration_s = float(row.get("total_duration_s", 0.0) or 0.0)
    platform_count = int(row.get("fit_usable_platform_count", 0) or 0)
    fit_r2 = _bounded(row.get("mean_speed_fit_r2"))
    components = {
        "tracking": _bounded(row.get("score_total")),
        "continuity": _bounded(1.0 - missing_ratio),
        "duration": _bounded(duration_s / max(float(thresholds["target_duration_s"]), 1e-6)),
        "platforms": _bounded(platform_count / max(int(thresholds["min_platforms"]), 1)),
        "fit": fit_r2,
        "drift": _bounded(row.get("drift_score"), 0.5),
        "grid_clear": _bounded(row.get("grid_clear_fraction"), 1.0),
        "roi_clear": _bounded(row.get("roi_clear_fraction"), 1.0),
    }
    weights = quality_cfg["trajectory_weights"]
    weight_sum = sum(float(weights.get(name, 0.0)) for name in components)
    score = sum(components[name] * float(weights.get(name, 0.0)) for name in components) / max(weight_sum, 1e-12)
    reasons: list[str] = []
    if missing_ratio > float(thresholds["max_missing_ratio"]):
        reasons.append("excessive_missing_ratio")
    if duration_s < float(thresholds["min_duration_s"]):
        reasons.append("track_too_short")
    if platform_count < int(thresholds["min_platforms"]):
        reasons.append("insufficient_stable_platforms")
    if fit_r2 < float(thresholds["min_speed_fit_r2"]):
        reasons.append("low_speed_fit_r2")
    if float(row.get("max_step_px", 0.0) or 0.0) > float(thresholds["max_frame_jump_px"]):
        reasons.append("excessive_frame_jump")
    if float(row.get("area_cv", 0.0) or 0.0) > float(thresholds["max_area_cv"]):
        reasons.append("unstable_blob_area")
    return _bounded(score), reasons


def score_drop_quality(
    candidate_summary: pd.DataFrame,
    drop_results: list[dict[str, object]],
    config: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    quality_cfg = config["quality"]
    drops_by_track = {str(drop.get("track_id", "")): drop for drop in drop_results}
    rows: list[dict[str, object]] = []
    for candidate in candidate_summary.to_dict("records"):
        track_id = str(candidate.get("candidate_id", ""))
        drop = drops_by_track.get(track_id, {})
        trajectory_score, reasons = _trajectory_score(candidate, config)
        q_valid = bool(drop.get("valid"))
        physics_score = _bounded(drop.get("quality_score")) if q_valid else 0.0
        if not q_valid:
            reasons.append("q_invalid")
        reasons.extend(str(flag) for flag in drop.get("flags", []) if str(flag))
        reasons = list(dict.fromkeys(reasons))
        score_weights = quality_cfg["stage_weights"]
        quality_score = _bounded(
            float(score_weights["trajectory"]) * trajectory_score
            + float(score_weights["physics"]) * physics_score
        )
        keep = not reasons and q_valid and quality_score >= float(quality_cfg["quality_threshold"])
        if not keep and not reasons:
            reasons.append("quality_score_below_threshold")
        rows.append(
            {
                "track_id": track_id,
                "drop_id": str(drop.get("drop_id", "")),
                "trajectory_score": trajectory_score,
                "physics_quality_score": physics_score,
                "quality_score": quality_score,
                "hard_rule_pass": not any(
                    reason
                    in {
                        "excessive_missing_ratio",
                        "track_too_short",
                        "insufficient_stable_platforms",
                        "low_speed_fit_r2",
                        "excessive_frame_jump",
                        "unstable_blob_area",
                    }
                    for reason in reasons
                ),
                "q_valid": q_valid,
                "keep": keep,
                "reject_reasons": ",".join(reasons),
            }
        )
    scores = pd.DataFrame(rows)
    reason_counts = Counter(
        reason
        for value in scores.get("reject_reasons", pd.Series(dtype=str)).astype(str)
        for reason in value.split(",")
        if reason
    )
    report = {
        "schema_version": 1,
        "mode": "mock_rule_adapter",
        "model_version": str(quality_cfg["model_version"]),
        "trained": False,
        "ml_training": False,
        "predicts_q": False,
        "quality_threshold": float(quality_cfg["quality_threshold"]),
        "weights": {
            "trajectory": quality_cfg["trajectory_weights"],
            "stages": quality_cfg["stage_weights"],
        },
        "total_track_count": int(len(scores)),
        "kept_track_count": int(scores["keep"].sum()) if not scores.empty else 0,
        "rejected_track_count": int((~scores["keep"]).sum()) if not scores.empty else 0,
        "reject_reason_counts": dict(sorted(reason_counts.items())),
        "scores": scores.to_dict("records"),
    }
    return scores, report


def filter_kept_drop_results(
    drop_results: list[dict[str, object]],
    scores: pd.DataFrame,
) -> list[dict[str, object]]:
    if scores.empty:
        return []
    kept_track_ids = set(scores.loc[scores["keep"].astype(bool), "track_id"].astype(str))
    return [
        drop
        for drop in drop_results
        if bool(drop.get("valid")) and str(drop.get("track_id", "")) in kept_track_ids
    ]
