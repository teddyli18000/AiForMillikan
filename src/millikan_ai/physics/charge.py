from __future__ import annotations

import math

import numpy as np
import pandas as pd


def eta_eff(radius_m: float, eta: float, pressure: float, cunningham_b: float) -> float:
    return eta / (1.0 + cunningham_b / (pressure * max(radius_m, 1e-18)))


def solve_radius_with_cunningham(alpha: float, constants: dict) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    if alpha <= 0:
        return None, ["non_positive_alpha"]
    eta = float(constants["air_viscosity_Pa_s"])
    rho = float(constants["oil_density_kg_m3"])
    gravity = float(constants["gravity_m_s2"])
    pressure = float(constants["pressure_Pa"])
    cunningham_b = float(constants["cunningham_b_Pa_m"])
    radius = math.sqrt((9 * eta * alpha) / (2 * rho * gravity))
    tolerance = float(constants.get("radius_tolerance_m", 1e-12))
    max_iterations = int(constants.get("max_radius_iterations", 80))
    for _ in range(max_iterations):
        eff = eta_eff(radius, eta, pressure, cunningham_b)
        updated = math.sqrt((9 * eff * alpha) / (2 * rho * gravity))
        if abs(updated - radius) < tolerance:
            return updated, flags
        radius = updated
    flags.append("radius_iteration_not_converged")
    return radius, flags


def compute_drop_result(segments: pd.DataFrame, config: dict) -> dict[str, object]:
    stable = segments[segments["stable"].astype(bool)].copy() if not segments.empty else segments
    flags: list[str] = []
    if len(stable) < 2:
        return {
            "drop_id": "drop_001",
            "valid": False,
            "method": "multi_voltage_terminal_velocity_fitting",
            "flags": ["insufficient_stable_platforms"],
            "platforms": stable.to_dict("records") if not stable.empty else [],
            "fit": {},
            "result": {},
            "quality_score": 0.0,
        }
    constants = config["physics"]
    d = float(constants["plate_distance_m"])
    e_field = stable["voltage_V"].to_numpy(float) / d
    velocity = stable["vy_m_s"].to_numpy(float)
    if len(set(np.round(e_field, 6))) < 2:
        flags.append("insufficient_distinct_voltages")
    coeffs, cov = np.polyfit(e_field, velocity, 1, cov=True) if len(stable) > 2 else (np.polyfit(e_field, velocity, 1), np.zeros((2, 2)))
    beta = float(coeffs[0])
    alpha = float(coeffs[1])
    radius, radius_flags = solve_radius_with_cunningham(alpha, constants)
    flags.extend(radius_flags)
    if radius is None:
        return {
            "drop_id": "drop_001",
            "valid": False,
            "method": "multi_voltage_terminal_velocity_fitting",
            "flags": flags,
            "platforms": stable.to_dict("records"),
            "fit": {"alpha": alpha, "beta": beta, "covariance": cov.tolist()},
            "result": {},
            "quality_score": 0.2,
        }
    eff = eta_eff(radius, float(constants["air_viscosity_Pa_s"]), float(constants["pressure_Pa"]), float(constants["cunningham_b_Pa_m"]))
    charge = 6 * math.pi * eff * radius * beta
    residuals = (velocity - (beta * e_field + alpha)).tolist()
    valid = not flags
    return {
        "drop_id": "drop_001",
        "valid": valid,
        "method": "multi_voltage_terminal_velocity_fitting",
        "constants": constants,
        "platforms": stable.to_dict("records"),
        "fit": {"alpha": alpha, "beta": beta, "covariance": cov.tolist(), "residuals": residuals},
        "result": {
            "radius_m": radius,
            "charge_C": charge,
            "charge_abs_C": abs(charge),
            "sigma_charge_C": abs(charge) * 0.15,
        },
        "quality_score": 0.8 if valid else 0.45,
        "flags": flags,
    }

