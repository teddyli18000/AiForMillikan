import json
import math

import numpy as np
import pytest

from millikan_ai.config import load_config
from millikan_ai.elementary.estimate import estimate_elementary_charge
from millikan_ai.elementary.plots import build_elementary_plots_data


def _config() -> dict:
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 0
    config["elementary"]["null_simulation_samples"] = 0
    config["elementary"]["skip_stability_diagnostics"] = True
    config["elementary"]["profile_grid_points"] = 180
    config["elementary"]["tau_lambda_profile_optimize_points"] = 2
    config["elementary"]["tau_lambda_optimizer_maxiter"] = 12
    return config


def _drops(charges: list[float], *, sigma_C: float = 0.05e-19) -> list[dict]:
    return [
        {
            "drop_id": f"drop_{index:03d}",
            "track_id": f"track_{index:03d}",
            "valid": True,
            "flags": [],
            "result": {
                "charge_abs_C": float(charge),
                "sigma_charge_C": float(sigma_C),
                "sigma_charge_random_C": float(sigma_C),
            },
        }
        for index, charge in enumerate(charges, start=1)
    ]


def _assert_json_safe(payload: dict) -> None:
    json.dumps(payload, allow_nan=False)


def test_plots_data_contains_four_interactive_charts_for_quantized_sample():
    e_true = 1.6e-19
    drops = _drops([n * e_true for n in [2, 3, 4, 5, 6, 7]])
    result = estimate_elementary_charge(drops, _config())

    plots = build_elementary_plots_data(result, drops)

    _assert_json_safe(plots)
    assert plots["schema_version"] == 2
    assert plots["status"] in {"diagnostic", "partial", "success"}
    assert set(plots["charts"]) == {
        "charge_distribution",
        "integer_assignment",
        "phase_residual",
        "model_comparison",
    }
    observations = plots["charts"]["charge_distribution"]["observations"]
    assert len(observations) == result["num_used_drops"]
    levels = plots["charts"]["charge_distribution"]["quantized_levels"]
    assert levels
    e_hat = result["elementary_charge"]["e_hat_C"]
    assert levels[0]["n"] == 1
    assert levels[0]["charge_C"] == pytest.approx(e_hat)
    assert levels[-1]["charge_C"] == pytest.approx(levels[-1]["n"] * e_hat)
    assert plots["charts"]["charge_distribution"]["quantized_density"]
    assert plots["charts"]["charge_distribution"]["continuous_density"]


def test_plots_data_links_drop_fields_across_charts_and_model_comparison():
    e_true = 1.6e-19
    drops = _drops([n * e_true + offset for n, offset in zip([2, 3, 4, 5, 6], [0.0, 0.01e-19, -0.01e-19, 0.0, 0.02e-19])])
    result = estimate_elementary_charge(drops, _config())

    plots = build_elementary_plots_data(result, drops)

    charge_points = {row["drop_id"]: row for row in plots["charts"]["charge_distribution"]["observations"]}
    assignment_points = {row["drop_id"]: row for row in plots["charts"]["integer_assignment"]["points"]}
    phase_points = {row["drop_id"]: row for row in plots["charts"]["phase_residual"]["points"]}
    contribution_points = {row["drop_id"]: row for row in plots["charts"]["model_comparison"]["per_drop"]}
    assert set(charge_points) == set(assignment_points) == set(phase_points) == set(contribution_points)
    for drop_id, point in assignment_points.items():
        charge = charge_points[drop_id]["q_C"]
        assert point["q_C"] == pytest.approx(charge)
        assert point["residual_C"] == pytest.approx(charge - point["nearest_quantized_charge_C"])
        assert phase_points[drop_id]["n_hat"] == point["n_hat"]
        assert -0.5 <= phase_points[drop_id]["phase_residual"] <= 0.5

    delta_sum = sum(row["delta_log_predictive_density"] for row in contribution_points.values())
    assert delta_sum == pytest.approx(plots["charts"]["model_comparison"]["delta_elpd"])


def test_plots_data_keeps_supported_separate_from_favored_for_continuous_data():
    values = (np.array([2.15, 2.62, 3.08, 3.76, 4.41, 5.07]) * 1e-19).tolist()
    drops = _drops(values, sigma_C=0.08e-19)
    result = estimate_elementary_charge(drops, _config())

    plots = build_elementary_plots_data(result, drops)

    _assert_json_safe(plots)
    assert plots["charts"]["charge_distribution"]["quantized_density"]
    assert plots["charts"]["charge_distribution"]["continuous_density"]
    assert "quantization_favored" in plots["summary"]
    assert plots["summary"]["quantization_supported"] is not True
    assert plots["summary"]["fundamental_spacing_identified"] is False


def test_plots_data_degrades_legally_for_insufficient_data():
    e_true = 1.6e-19
    drops = _drops([2 * e_true])
    result = estimate_elementary_charge(drops, _config())

    plots = build_elementary_plots_data(result, drops)

    _assert_json_safe(plots)
    assert plots["status"] == "insufficient_data"
    assert plots["reason"]
    assert len(plots["charts"]["charge_distribution"]["observations"]) == 1
    assert plots["charts"]["charge_distribution"]["quantized_density"] == []
    assert plots["charts"]["charge_distribution"]["continuous_density"] == []
    assert plots["charts"]["model_comparison"]["status"] == "unavailable"
