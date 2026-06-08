from __future__ import annotations

import pandas as pd

from millikan_ai.config import load_config
from millikan_ai.quality.rules import filter_kept_drop_results, score_drop_quality


def _candidate_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_id": "candidate_001",
                "total_duration_s": 6.0,
                "missing_ratio": 0.02,
                "score_total": 0.9,
                "fit_usable_platform_count": 3,
                "mean_speed_fit_r2": 0.98,
                "drift_score": 0.95,
                "grid_clear_fraction": 0.9,
                "roi_clear_fraction": 0.95,
                "reject_reason": "",
            },
            {
                "candidate_id": "candidate_002",
                "total_duration_s": 2.0,
                "missing_ratio": 0.65,
                "score_total": 0.35,
                "fit_usable_platform_count": 1,
                "mean_speed_fit_r2": 0.4,
                "drift_score": 0.3,
                "grid_clear_fraction": 0.8,
                "roi_clear_fraction": 0.9,
                "reject_reason": "insufficient_stable_platform_fits",
            },
            {
                "candidate_id": "candidate_003",
                "total_duration_s": 6.0,
                "missing_ratio": 0.01,
                "score_total": 0.9,
                "fit_usable_platform_count": 3,
                "mean_speed_fit_r2": 0.98,
                "drift_score": 0.95,
                "grid_clear_fraction": 0.9,
                "roi_clear_fraction": 0.95,
                "max_step_px": 24.0,
                "area_cv": 0.6,
                "reject_reason": "",
            },
        ]
    )


def _drop_results() -> list[dict[str, object]]:
    return [
        {
            "drop_id": "drop_001",
            "track_id": "candidate_001",
            "valid": True,
            "quality_score": 0.8,
            "flags": [],
            "fit": {"alpha": 1.0e-4, "beta": 1.0e-9, "residuals": [0.0, 1.0e-7]},
            "result": {"charge_abs_C": 3.2e-19, "sigma_charge_C": 0.3e-19},
        },
        {
            "drop_id": "drop_002",
            "track_id": "candidate_002",
            "valid": False,
            "quality_score": 0.2,
            "flags": ["non_positive_alpha"],
            "fit": {"alpha": -1.0e-4, "beta": 1.0e-9},
            "result": {},
        },
        {
            "drop_id": "drop_003",
            "track_id": "candidate_003",
            "valid": True,
            "quality_score": 0.8,
            "flags": [],
            "fit": {"alpha": 1.0e-4, "beta": 1.0e-9, "residuals": [0.0, 1.0e-7]},
            "result": {"charge_abs_C": 4.8e-19, "sigma_charge_C": 0.3e-19},
        },
    ]


def test_mock_quality_adapter_is_deterministic_and_explainable():
    config = load_config("configs/default.yaml")

    first_scores, first_report = score_drop_quality(_candidate_summary(), _drop_results(), config)
    second_scores, second_report = score_drop_quality(_candidate_summary(), _drop_results(), config)

    pd.testing.assert_frame_equal(first_scores, second_scores)
    assert first_report == second_report
    assert first_report["mode"] == "mock_rule_adapter"
    assert first_report["trained"] is False
    assert first_report["ml_training"] is False
    assert first_scores["quality_score"].between(0.0, 1.0).all()
    assert first_scores.set_index("track_id").loc["candidate_001", "keep"]
    rejected = first_scores.set_index("track_id").loc["candidate_002"]
    assert not rejected["keep"]
    assert "q_invalid" in rejected["reject_reasons"]
    jumpy = first_scores.set_index("track_id").loc["candidate_003"]
    assert not jumpy["keep"]
    assert "excessive_frame_jump" in jumpy["reject_reasons"]
    assert "unstable_blob_area" in jumpy["reject_reasons"]


def test_elementary_input_only_contains_kept_valid_drops():
    config = load_config("configs/default.yaml")
    scores, _report = score_drop_quality(_candidate_summary(), _drop_results(), config)

    kept = filter_kept_drop_results(_drop_results(), scores)

    assert [drop["track_id"] for drop in kept] == ["candidate_001"]
