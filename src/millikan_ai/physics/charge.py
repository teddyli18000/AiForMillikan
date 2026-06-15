from __future__ import annotations

import math

import numpy as np
import pandas as pd

from millikan_ai.physics.viscosity import resolve_air_viscosity


def eta_eff(radius_m: float, eta: float, pressure: float, cunningham_b: float) -> float:
    if radius_m <= 0 or eta <= 0 or pressure <= 0 or cunningham_b < 0:
        raise ValueError("non_positive_cunningham_parameter")
    return eta / (1.0 + cunningham_b / (pressure * radius_m))


def solve_radius_with_cunningham(alpha: float, constants: dict) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    if alpha <= 0:
        return None, ["non_positive_alpha"]
    eta = float(constants.get("air_viscosity_Pa_s") or resolve_air_viscosity({"physics": constants}).get("air_viscosity_Pa_s"))
    rho = float(constants["oil_density_kg_m3"])
    gravity = float(constants["gravity_m_s2"])
    pressure = float(constants["pressure_Pa"])
    cunningham_b = float(constants["cunningham_b_Pa_m"])
    if eta <= 0 or rho <= 0 or gravity <= 0 or pressure <= 0 or cunningham_b < 0:
        return None, ["non_positive_physics_parameter"]
    c = cunningham_b / pressure
    k = (9 * eta * float(alpha)) / (2 * rho * gravity)
    discriminant = c * c + 4 * k
    if not math.isfinite(discriminant) or discriminant <= 0:
        return None, ["non_finite_radius_solution"]
    radius = (2 * k) / (c + math.sqrt(discriminant))
    if not math.isfinite(radius) or radius <= 0:
        return None, ["non_finite_radius_solution"]
    return radius, flags


def fit_velocity_voltage(platforms: pd.DataFrame) -> dict[str, object]:
    required = {"voltage_V", "vy_m_s"}
    missing = required.difference(platforms.columns)
    if missing:
        raise ValueError(f"missing_columns:{','.join(sorted(missing))}")
    frame = platforms.copy()
    frame = frame[np.isfinite(frame["voltage_V"].to_numpy(float)) & np.isfinite(frame["vy_m_s"].to_numpy(float))]
    if len(frame) < 2:
        raise ValueError("insufficient_platforms")
    voltage = frame["voltage_V"].to_numpy(float)
    velocity = frame["vy_m_s"].to_numpy(float)
    if len(set(np.round(voltage, 9))) < 2:
        raise ValueError("insufficient_distinct_voltages")
    design = np.column_stack([np.ones(len(voltage)), -voltage])
    if "sigma_vy" in frame:
        sigma = frame["sigma_vy"].to_numpy(float)
    elif "sigma_velocity_random_m_s" in frame:
        sigma = frame["sigma_velocity_random_m_s"].to_numpy(float)
    else:
        sigma = np.asarray([], dtype=float)
    valid_sigma = len(sigma) == len(frame) and bool(np.all(np.isfinite(sigma) & (sigma > 0)))
    if valid_sigma:
        weights = 1.0 / np.square(sigma)
        xtw = design.T * weights
        normal = xtw @ design
        try:
            covariance = np.linalg.inv(normal)
        except np.linalg.LinAlgError as exc:
            raise ValueError("singular_voltage_design") from exc
        theta = covariance @ (xtw @ velocity)
        fit_method = "weighted_least_squares"
        velocity_uncertainty_source = "provided_sigma_v"
    else:
        try:
            theta, _residual_sum, _rank, _singular = np.linalg.lstsq(design, velocity, rcond=None)
            xtx_inv = np.linalg.inv(design.T @ design)
        except np.linalg.LinAlgError as exc:
            raise ValueError("singular_voltage_design") from exc
        predicted_unscaled = design @ theta
        residuals_unscaled = velocity - predicted_unscaled
        dof_unscaled = len(voltage) - 2
        if dof_unscaled > 0:
            residual_variance = float(np.sum(np.square(residuals_unscaled)) / dof_unscaled)
            covariance = xtx_inv * residual_variance
        else:
            covariance = np.full((2, 2), math.nan, dtype=float)
        sigma = np.full(len(frame), math.nan, dtype=float)
        fit_method = "unweighted_least_squares"
        velocity_uncertainty_source = "unavailable_unweighted"
    alpha = float(theta[0])
    gamma = float(theta[1])
    predicted = design @ theta
    residuals = velocity - predicted
    chi_square = float(np.sum(np.square(residuals / sigma))) if valid_sigma else math.nan
    dof = max(0, len(voltage) - 2)
    voltage_span = float(np.max(voltage) - np.min(voltage))
    condition = float(np.linalg.cond(design))
    intercept_ratio = float(max(abs(np.min(voltage)), abs(np.max(voltage))) / voltage_span) if voltage_span > 0 else math.inf
    sigma_alpha = math.sqrt(max(0.0, float(covariance[0, 0]))) if math.isfinite(float(covariance[0, 0])) else math.inf
    sigma_gamma = math.sqrt(max(0.0, float(covariance[1, 1]))) if math.isfinite(float(covariance[1, 1])) else math.inf
    return {
        "fit_method": fit_method,
        "velocity_uncertainty_source": velocity_uncertainty_source,
        "alpha_m_s": alpha,
        "gamma_m_s_V": gamma,
        "covariance": covariance.tolist(),
        "sigma_alpha_random": sigma_alpha,
        "sigma_gamma_random": sigma_gamma,
        "residuals_m_s": residuals.tolist(),
        "fit_chi_square": chi_square,
        "fit_dof": dof,
        "fit_reduced_chi_square": chi_square / dof if dof > 0 else math.nan,
        "validation_level": "two_platform" if len(voltage) == 2 else "multi_platform",
        "voltage_span_V": voltage_span,
        "intercept_extrapolation_ratio": intercept_ratio,
        "design_matrix_condition_number": condition,
    }


def _charge_uncertainty(charge_abs: float, alpha: float, gamma: float, fit: dict[str, object]) -> float:
    sigma_alpha = float(fit.get("sigma_alpha_random", math.inf))
    sigma_gamma = float(fit.get("sigma_gamma_random", math.inf))
    if alpha <= 0 or gamma <= 0 or not math.isfinite(charge_abs):
        return math.inf
    terms = []
    if math.isfinite(sigma_alpha):
        terms.append((0.5 * sigma_alpha / alpha) ** 2)
    if math.isfinite(sigma_gamma):
        terms.append((sigma_gamma / gamma) ** 2)
    if not terms:
        return math.inf
    return abs(charge_abs) * math.sqrt(sum(terms))


def _random_uncertainty_monte_carlo(
    alpha: float,
    gamma: float,
    fit: dict[str, object],
    constants: dict,
    viscosity: dict,
    samples: int,
    seed: int,
) -> dict[str, object]:
    covariance = np.asarray(fit.get("covariance", []), dtype=float)
    if samples <= 0 or covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
        return {
            "uncertainty_method": "unavailable",
            "random_mc_samples_requested": int(max(0, samples)),
            "random_mc_samples_used": 0,
            "sigma_radius_random_m": math.inf,
            "radius_ci95_low_m": math.nan,
            "radius_ci95_high_m": math.nan,
            "sigma_charge_random_C": math.inf,
            "charge_ci95_low_C": math.nan,
            "charge_ci95_high_C": math.nan,
        }
    covariance = (covariance + covariance.T) / 2.0
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    except np.linalg.LinAlgError:
        return {
            "uncertainty_method": "unavailable",
            "random_mc_samples_requested": int(samples),
            "random_mc_samples_used": 0,
            "sigma_radius_random_m": math.inf,
            "radius_ci95_low_m": math.nan,
            "radius_ci95_high_m": math.nan,
            "sigma_charge_random_C": math.inf,
            "charge_ci95_low_C": math.nan,
            "charge_ci95_high_C": math.nan,
        }
    eigenvalues = np.maximum(eigenvalues, 0.0)
    covariance_psd = (eigenvectors * eigenvalues) @ eigenvectors.T
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(np.array([alpha, gamma], dtype=float), covariance_psd, size=int(samples), check_valid="ignore")
    radius_samples: list[float] = []
    charge_samples: list[float] = []
    eta = float(viscosity["air_viscosity_Pa_s"])
    pressure = float(constants["pressure_Pa"])
    b = float(constants["cunningham_b_Pa_m"])
    d = float(constants["plate_distance_m"])
    for alpha_i, gamma_i in draws:
        if not (math.isfinite(float(alpha_i)) and math.isfinite(float(gamma_i))) or alpha_i <= 0 or gamma_i <= 0:
            continue
        radius_i, flags = solve_radius_with_cunningham(float(alpha_i), constants)
        if flags or radius_i is None:
            continue
        try:
            eff_i = eta_eff(radius_i, eta, pressure, b)
        except ValueError:
            continue
        charge_i = 6 * math.pi * eff_i * radius_i * d * float(gamma_i)
        if math.isfinite(charge_i) and charge_i > 0:
            radius_samples.append(float(radius_i))
            charge_samples.append(float(charge_i))
    if len(charge_samples) < 2:
        return {
            "uncertainty_method": "joint_alpha_gamma_monte_carlo",
            "random_mc_samples_requested": int(samples),
            "random_mc_samples_used": int(len(charge_samples)),
            "sigma_radius_random_m": math.inf,
            "radius_ci95_low_m": math.nan,
            "radius_ci95_high_m": math.nan,
            "sigma_charge_random_C": math.inf,
            "charge_ci95_low_C": math.nan,
            "charge_ci95_high_C": math.nan,
        }
    radius_arr = np.asarray(radius_samples, dtype=float)
    charge_arr = np.asarray(charge_samples, dtype=float)
    return {
        "uncertainty_method": "joint_alpha_gamma_monte_carlo",
        "random_mc_samples_requested": int(samples),
        "random_mc_samples_used": int(len(charge_arr)),
        "sigma_radius_random_m": float(np.std(radius_arr, ddof=1)),
        "radius_ci95_low_m": float(np.percentile(radius_arr, 2.5)),
        "radius_ci95_high_m": float(np.percentile(radius_arr, 97.5)),
        "sigma_charge_random_C": float(np.std(charge_arr, ddof=1)),
        "charge_ci95_low_C": float(np.percentile(charge_arr, 2.5)),
        "charge_ci95_high_C": float(np.percentile(charge_arr, 97.5)),
    }


def _invalid_result(flags: list[str], platforms: pd.DataFrame, fit: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "drop_id": "drop_001",
        "valid": False,
        "method": "multi_voltage_terminal_velocity_fitting",
        "flags": flags,
        "platforms": platforms.to_dict("records") if not platforms.empty else [],
        "fit": fit or {},
        "result": {},
    }


def compute_drop_result(segments: pd.DataFrame, config: dict) -> dict[str, object]:
    stable = segments[segments["stable"].astype(bool)].copy() if not segments.empty else segments
    flags: list[str] = []
    if len(stable) < 2:
        return _invalid_result(["insufficient_platforms"], stable)
    constants = {**config["physics"], **resolve_air_viscosity(config)}
    viscosity = resolve_air_viscosity(config)
    d = float(constants["plate_distance_m"])
    if d <= 0:
        return _invalid_result(["non_positive_plate_distance"], stable)
    try:
        fit = fit_velocity_voltage(stable)
    except ValueError as exc:
        return _invalid_result([str(exc)], stable)
    alpha = float(fit["alpha_m_s"])
    gamma = float(fit["gamma_m_s_V"])
    if alpha <= 0:
        flags.append("non_positive_alpha")
    if gamma <= 0:
        flags.append("non_positive_gamma")
    radius, radius_flags = solve_radius_with_cunningham(alpha, constants)
    flags.extend(radius_flags)
    if flags or radius is None:
        return _invalid_result(flags, stable, fit)
    eff = eta_eff(radius, float(viscosity["air_viscosity_Pa_s"]), float(constants["pressure_Pa"]), float(constants["cunningham_b_Pa_m"]))
    charge_abs = 6 * math.pi * eff * radius * d * gamma
    random_mc = _random_uncertainty_monte_carlo(
        alpha,
        gamma,
        fit,
        constants,
        viscosity,
        int(config.get("physics", {}).get("random_mc_samples", 1000)),
        int(config.get("elementary", {}).get("random_seed", 42)),
    )
    sigma_charge = float(random_mc.get("sigma_charge_random_C", math.inf))
    if not math.isfinite(sigma_charge):
        sigma_charge = _charge_uncertainty(charge_abs, alpha, gamma, fit)
    return {
        "drop_id": "drop_001",
        "valid": True,
        "method": "multi_voltage_terminal_velocity_fitting",
        "constants": {**constants, **viscosity},
        "platforms": stable.to_dict("records"),
        "fit": {
            **fit,
            "alpha": alpha,
            "gamma": gamma,
            "direction_convention": "+Y_down_positive_voltage_pushes_up",
        },
        "result": {
            "radius_m": radius,
            "charge_C": charge_abs,
            "charge_abs_C": charge_abs,
            "sigma_charge_C": sigma_charge,
            **random_mc,
            "sigma_charge_systematic_C": 0.0,
            "sigma_charge_total_C": sigma_charge,
        },
        "flags": flags,
    }
