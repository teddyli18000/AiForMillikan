import math

import numpy as np
import pandas as pd
import pytest

from millikan_ai.config import load_config
from millikan_ai.physics.charge import (
    compute_drop_result,
    eta_eff,
    fit_velocity_voltage,
    solve_radius_with_cunningham,
)
from millikan_ai.physics.viscosity import resolve_air_viscosity


def _physics_constants(config: dict) -> dict:
    return {**config["physics"], **resolve_air_viscosity(config)}


def _synthetic_segments_for_radius_charge(config: dict, radius: float, charge: float, voltages: tuple[float, ...]) -> pd.DataFrame:
    constants = _physics_constants(config)
    eta = constants["air_viscosity_Pa_s"]
    pressure = constants["pressure_Pa"]
    b = constants["cunningham_b_Pa_m"]
    d = constants["plate_distance_m"]
    rho = constants["oil_density_kg_m3"]
    gravity = constants["gravity_m_s2"]
    eff = eta_eff(radius, eta, pressure, b)
    alpha = (2 * rho * gravity * radius**2) / (9 * eff)
    gamma = charge / (6 * math.pi * eff * radius * d)
    return pd.DataFrame(
        [
            {
                "platform_id": f"P{index:03d}",
                "track_id": "accepted_001",
                "voltage_V": voltage,
                "vy_m_s": alpha - gamma * voltage,
                "sigma_vy": 1.0e-7,
                "stable": True,
            }
            for index, voltage in enumerate(voltages, start=1)
        ]
    )


def test_cunningham_closed_form_satisfies_radius_equation():
    config = load_config("configs/default.yaml")
    constants = _physics_constants(config)
    alpha = 2.2e-4

    radius, flags = solve_radius_with_cunningham(alpha, constants)

    assert flags == []
    eta = constants["air_viscosity_Pa_s"]
    rho = constants["oil_density_kg_m3"]
    gravity = constants["gravity_m_s2"]
    pressure = constants["pressure_Pa"]
    b = constants["cunningham_b_Pa_m"]
    residual = alpha - (2 * rho * gravity * radius**2) / (9 * eta_eff(radius, eta, pressure, b))
    assert residual == pytest.approx(0.0, abs=1e-15)


def test_fit_velocity_voltage_two_platforms_has_nonzero_covariance():
    rows = pd.DataFrame(
        [
            {"voltage_V": 0.0, "vy_m_s": 2.0e-4, "sigma_vy": 2.0e-6},
            {"voltage_V": 200.0, "vy_m_s": 1.0e-4, "sigma_vy": 2.0e-6},
        ]
    )

    fit = fit_velocity_voltage(rows)

    assert fit["alpha_m_s"] == pytest.approx(2.0e-4)
    assert fit["gamma_m_s_V"] == pytest.approx(5.0e-7)
    assert fit["covariance"][0][0] > 0
    assert fit["covariance"][1][1] > 0
    assert fit["validation_level"] == "two_platform"
    assert fit["fit_method"] == "weighted_least_squares"


def test_fit_velocity_voltage_without_sigma_uses_explicit_unweighted_fallback():
    rows = pd.DataFrame(
        [
            {"voltage_V": 100.0, "vy_m_s": 1.5e-4},
            {"voltage_V": 300.0, "vy_m_s": 0.5e-4},
        ]
    )

    fit = fit_velocity_voltage(rows)

    assert fit["alpha_m_s"] == pytest.approx(2.0e-4)
    assert fit["gamma_m_s_V"] == pytest.approx(5.0e-7)
    assert fit["fit_method"] == "unweighted_least_squares"
    assert fit["velocity_uncertainty_source"] == "unavailable_unweighted"


def test_compute_drop_result_recovers_known_radius_and_charge():
    config = load_config("configs/default.yaml")
    constants = _physics_constants(config)
    radius = 0.75e-6
    charge = 4.8e-19
    eta = constants["air_viscosity_Pa_s"]
    pressure = constants["pressure_Pa"]
    b = constants["cunningham_b_Pa_m"]
    d = constants["plate_distance_m"]
    rho = constants["oil_density_kg_m3"]
    gravity = constants["gravity_m_s2"]
    eff = eta_eff(radius, eta, pressure, b)
    alpha = (2 * rho * gravity * radius**2) / (9 * eff)
    gamma = charge / (6 * math.pi * eff * radius * d)
    rows = []
    for voltage in (0.0, 180.0, 360.0):
        rows.append(
            {
                "platform_id": f"P{len(rows)+1:03d}",
                "track_id": "candidate_001",
                "voltage_V": voltage,
                "vy_m_s": alpha - gamma * voltage,
                "sigma_vy": 1.0e-7,
                "stable": True,
            }
        )

    result = compute_drop_result(pd.DataFrame(rows), config)

    assert result["valid"] is True
    assert result["result"]["radius_m"] == pytest.approx(radius, rel=1e-9)
    assert result["result"]["charge_abs_C"] == pytest.approx(charge, rel=1e-9)
    assert not math.isclose(result["result"]["sigma_charge_C"], abs(charge) * 0.15, rel_tol=1e-12, abs_tol=0.0)
    assert "quality_score" not in result


@pytest.mark.parametrize(
    "voltages",
    [
        (0.0, 250.0),
        (100.0, 250.0),
        (0.0, 234.988155),
        (0.0, 180.0, 360.0),
    ],
)
def test_compute_drop_result_known_truth_voltage_scenarios(voltages):
    config = load_config("configs/default.yaml")
    config["physics"]["random_mc_samples"] = 200
    radius = 0.72e-6
    charge = 4.8e-19

    result = compute_drop_result(_synthetic_segments_for_radius_charge(config, radius, charge, voltages), config)

    assert result["valid"] is True
    assert result["fit"]["alpha_m_s"] > 0
    assert result["fit"]["gamma_m_s_V"] > 0
    assert result["result"]["radius_m"] == pytest.approx(radius, rel=1e-9)
    assert result["result"]["charge_abs_C"] == pytest.approx(charge, rel=1e-9)


def test_compute_drop_result_joint_monte_carlo_uncertainty_outputs():
    config = load_config("configs/default.yaml")
    config["physics"]["random_mc_samples"] = 400
    radius = 0.75e-6
    charge = 4.8e-19
    rows = _synthetic_segments_for_radius_charge(config, radius, charge, (0.0, 180.0, 360.0))

    result = compute_drop_result(rows, config)

    assert result["valid"] is True
    output = result["result"]
    assert output["uncertainty_method"] == "joint_alpha_gamma_monte_carlo"
    assert output["random_mc_samples_used"] > 100
    assert output["sigma_radius_random_m"] > 0
    assert output["radius_ci95_low_m"] < output["radius_m"] < output["radius_ci95_high_m"]
    assert output["sigma_charge_random_C"] > 0
    assert output["charge_ci95_low_C"] < output["charge_abs_C"] < output["charge_ci95_high_C"]
    assert result["fit"]["covariance"][0][1] != 0


def test_compute_drop_result_fails_for_non_positive_gamma():
    config = load_config("configs/default.yaml")
    rows = pd.DataFrame(
        [
            {"platform_id": "P001", "voltage_V": 0.0, "vy_m_s": 1.0e-4, "sigma_vy": 1e-6, "stable": True},
            {"platform_id": "P002", "voltage_V": 200.0, "vy_m_s": 2.0e-4, "sigma_vy": 1e-6, "stable": True},
        ]
    )

    result = compute_drop_result(rows, config)

    assert result["valid"] is False
    assert "non_positive_gamma" in result["flags"]
