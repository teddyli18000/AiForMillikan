from __future__ import annotations

import math
from typing import Any

import numpy as np


def compute_q_with_uncertainty(fit: dict[str, Any], balance_voltage_V: float, scale_y_m_per_px: float, cfg: dict[str, Any]) -> dict[str, Any]:
    pcfg = cfg["physics"]
    flags: list[str] = []
    if not fit.get("valid"):
        flags.extend(fit.get("flags", []))
    if not math.isfinite(float(balance_voltage_V)) or float(balance_voltage_V) <= 0:
        flags.append("invalid_balance_voltage")
    velocity = float(fit.get("velocity_m_s") or math.nan)
    if not math.isfinite(velocity) or velocity <= 0:
        flags.append("invalid_velocity")
    if flags:
        return {
            "valid": False,
            "diagnostic_only": True,
            "flags": list(dict.fromkeys(flags)),
            "recovery_suggestions": fit.get("recovery_suggestions", ["重新测量该油滴或选择另一颗油滴。"]),
        }
    q = q_from_velocity(velocity, balance_voltage_V, pcfg)
    random = _random_uncertainty(velocity, fit, balance_voltage_V, pcfg)
    systematic = _systematic_uncertainty(velocity, balance_voltage_V, pcfg)
    sigma_random = random["sigma_q_random_C"]
    sigma_systematic = systematic["sigma_q_systematic_C"]
    sigma_total = math.sqrt(sigma_random**2 + sigma_systematic**2)
    incomplete = systematic["systematic_uncertainty_incomplete"]
    valid = all(math.isfinite(float(value)) and float(value) > 0 for value in [q["radius_m"], q["charge_abs_C"], sigma_total])
    out = {
        **q,
        **random,
        **systematic,
        "sigma_q_total_C": sigma_total,
        "q_ci95_C": [max(0.0, q["charge_abs_C"] - 1.96 * sigma_total), q["charge_abs_C"] + 1.96 * sigma_total],
        "valid": bool(valid),
        "diagnostic_only": not bool(valid),
        "flags": ["systematic_uncertainty_incomplete"] if incomplete else [],
        "recovery_suggestions": [] if valid else ["不确定度不可用，保留为诊断记录并重新测量。"],
    }
    return out


def q_from_velocity(velocity_m_s: float, balance_voltage_V: float, pcfg: dict[str, Any]) -> dict[str, float]:
    eta = float(pcfg["air_viscosity_Pa_s"])
    rho = float(pcfg["oil_density_kg_m3"])
    g = float(pcfg["gravity_m_s2"])
    b = float(pcfg["cunningham_b_Pa_m"])
    p = float(pcfg["pressure_Pa"])
    d = float(pcfg["plate_distance_m"])
    bp = b / p
    radius = (math.sqrt(bp * bp + (18.0 * eta * velocity_m_s) / (rho * g)) - bp) / 2.0
    mass = 4.0 * math.pi * radius**3 * rho / 3.0
    charge = mass * g * d / float(balance_voltage_V)
    return {
        "velocity_m_s": float(velocity_m_s),
        "radius_m": float(radius),
        "mass_kg": float(mass),
        "charge_abs_C": abs(float(charge)),
    }


def _random_uncertainty(velocity: float, fit: dict[str, Any], voltage: float, pcfg: dict[str, Any]) -> dict[str, float]:
    r2 = float(fit.get("r2") or 0.0)
    rmse = max(0.0, float(fit.get("rmse_px") or 0.0))
    displacement = max(1e-9, abs(float(fit.get("displacement_px") or 0.0)))
    point_count = max(2, int(fit.get("fit_point_count") or 2))
    rel = max(1e-6, (rmse / displacement) * math.sqrt(12.0 / point_count) + max(0.0, 1.0 - r2) * 0.2)
    qs = []
    rng = np.random.default_rng(42)
    for _ in range(int(pcfg.get("random_bootstrap_samples", 300))):
        sampled_velocity = max(1e-12, rng.normal(velocity, abs(velocity) * rel))
        qs.append(q_from_velocity(float(sampled_velocity), voltage, pcfg)["charge_abs_C"])
    arr = np.asarray(qs, dtype=float)
    return {
        "sigma_q_random_C": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "q_random_ci95_C": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))] if len(arr) else [math.nan, math.nan],
    }


def _systematic_uncertainty(velocity: float, voltage: float, pcfg: dict[str, Any]) -> dict[str, Any]:
    ucfg = pcfg.get("systematic_uncertainty", {})
    rels = {
        "plate_distance_m": float(ucfg.get("plate_distance_rel", 0.0)),
        "voltage": float(ucfg.get("voltage_scale_rel", 0.0)),
        "air_viscosity_Pa_s": float(ucfg.get("air_viscosity_rel", 0.0)),
        "pressure_Pa": float(ucfg.get("pressure_rel", 0.0)),
        "oil_density_kg_m3": float(ucfg.get("oil_density_rel", 0.0)),
        "cunningham_b_Pa_m": float(ucfg.get("cunningham_b_rel", 0.0)),
    }
    incomplete = not any(value > 0 for value in rels.values())
    samples = int(pcfg.get("systematic_mc_samples", 300))
    if incomplete or samples <= 1:
        return {"sigma_q_systematic_C": 0.0, "systematic_uncertainty_incomplete": True, "q_systematic_ci95_C": None}
    rng = np.random.default_rng(2718)
    qs = []
    for _ in range(samples):
        draw = dict(pcfg)
        draw_voltage = voltage
        for key, rel in rels.items():
            if key == "voltage":
                draw_voltage = max(1e-12, rng.normal(voltage, abs(voltage) * rel))
            elif rel > 0:
                draw[key] = max(1e-30, rng.normal(float(pcfg[key]), abs(float(pcfg[key])) * rel))
        qs.append(q_from_velocity(velocity, draw_voltage, draw)["charge_abs_C"])
    arr = np.asarray(qs, dtype=float)
    return {
        "sigma_q_systematic_C": float(np.std(arr, ddof=1)),
        "systematic_uncertainty_incomplete": False,
        "q_systematic_ci95_C": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))],
    }

