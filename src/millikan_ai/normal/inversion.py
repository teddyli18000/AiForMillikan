from __future__ import annotations

import math
from typing import Any

import numpy as np


def run_weighted_integer_inversion(records: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    icfg = cfg["inversion"]
    eligible = _eligible_records(records)
    min_records = int(icfg.get("min_records", 3))
    if len(eligible) < min_records:
        return {
            "reliable": False,
            "status": "insufficient_eligible_records",
            "num_used": len(eligible),
            "valid_q_count": len(eligible),
            "min_required": min_records,
            "flags": ["insufficient_eligible_records"],
        }
    q = np.array([float(row["q"]["q_C"]) for row in eligible], dtype=float)
    sigma = np.array([float(row["q"]["sigma_q_C"]) for row in eligible], dtype=float)
    grid = np.linspace(float(icfg["e_min_C"]), float(icfg["e_max_C"]), int(icfg.get("grid_points", 900)))
    max_integer = int(icfg.get("max_integer", 80))
    scores = []
    assignments = []
    for e in grid:
        n = np.clip(np.rint(q / e), 1, max_integer)
        residual_sigma = (q - n * e) / sigma
        score = float(np.sum(residual_sigma**2))
        scores.append(score)
        assignments.append(n.astype(int))
    best_idx = int(np.argmin(scores))
    e_hat = float(grid[best_idx])
    n_hat = assignments[best_idx]
    residual = q - n_hat * e_hat
    residual_sigma = residual / sigma
    weighted_rms = math.sqrt(float(scores[best_idx]) / len(q))
    flags: list[str] = []
    if weighted_rms > float(icfg.get("max_weighted_rms", 2.5)):
        flags.append("weighted_residual_too_large")
    if math.gcd(*[int(value) for value in n_hat.tolist()]) > 1:
        flags.append("integer_assignments_nonprimitive")
    if best_idx in {0, len(grid) - 1}:
        flags.append("search_boundary_hit")
    return {
        "reliable": len(flags) == 0,
        "status": "reliable" if len(flags) == 0 else "diagnostic",
        "e_hat_C": e_hat,
        "sigma_e_C": _profile_sigma(grid, scores, best_idx),
        "weighted_rms": weighted_rms,
        "num_used": len(eligible),
        "valid_q_count": len(eligible),
        "search_interval_C": [float(grid[0]), float(grid[-1])],
        "assignments": [
            {
                "record_id": eligible[i]["record_id"],
                "q_C": float(q[i]),
                "sigma_q_C": float(sigma[i]),
                "n": int(n_hat[i]),
                "nearest_quantized_charge_C": float(n_hat[i] * e_hat),
                "residual_C": float(residual[i]),
                "residual_sigma": float(residual_sigma[i]),
            }
            for i in range(len(eligible))
        ],
        "profile": [{"e_C": float(grid[i]), "weighted_chi2": float(scores[i])} for i in range(len(grid))],
        "charts": _charts(q, sigma, n_hat, residual_sigma, e_hat),
        "plots_data": _charts(q, sigma, n_hat, residual_sigma, e_hat),
        "quantized": {"model": "integer_multiple_weighted_residual", "weighted_rms": weighted_rms, "favored": len(flags) == 0},
        "continuous": {"model": "continuous_charge_reference", "favored": False},
        "comparison": {"quantized_favored": len(flags) == 0, "continuous_favored": False, "status": "diagnostic" if flags else "reliable"},
        "flags": flags,
    }


def _eligible_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for record in records:
        q = record.get("q") or {}
        charge = float(q.get("q_C") or q.get("charge_abs_C") or math.nan)
        sigma = float(q.get("sigma_q_C") or q.get("sigma_q_random_C") or math.nan)
        if record.get("kept") and record.get("status") == "valid" and q.get("valid") and math.isfinite(charge) and charge > 0 and math.isfinite(sigma) and sigma > 0:
            out.append(record)
    return out


def _charts(q: np.ndarray, sigma: np.ndarray, n_hat: np.ndarray, residual_sigma: np.ndarray, e_hat: float) -> dict[str, Any]:
    return {
        "charge_distribution": [
            {"q_C": float(q[i]), "sigma_q_C": float(sigma[i]), "n": int(n_hat[i]), "nearest_C": float(n_hat[i] * e_hat)}
            for i in range(len(q))
        ],
        "residuals": [
            {"q_C": float(q[i]), "residual_sigma": float(residual_sigma[i]), "n": int(n_hat[i])}
            for i in range(len(q))
        ],
        "quantized_levels": [
            {"n": int(n), "charge_C": float(n * e_hat)}
            for n in range(1, int(np.max(n_hat)) + 2)
        ],
        "continuous_reference": [
            {"q_C": float(value)}
            for value in np.linspace(float(np.min(q)), float(np.max(q)), 80)
        ],
    }


def _profile_sigma(grid: np.ndarray, scores: list[float], best_idx: int) -> float | None:
    if len(grid) < 3:
        return None
    best = float(scores[best_idx])
    accepted = [float(grid[i]) for i, score in enumerate(scores) if float(score) <= best + 1.0]
    if len(accepted) < 2:
        spacing = float(abs(grid[min(best_idx + 1, len(grid) - 1)] - grid[max(best_idx - 1, 0)]))
        return spacing if math.isfinite(spacing) and spacing > 0 else None
    sigma = (max(accepted) - min(accepted)) / 2.0
    return sigma if math.isfinite(sigma) and sigma > 0 else None
