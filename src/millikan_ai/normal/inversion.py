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
    sigma_raw = np.array([float(row["q"]["sigma_q_C"]) for row in eligible], dtype=float)
    sigma_floor = max(0.0, float(icfg.get("sigma_floor_C", 0.0)))
    sigma = np.sqrt(sigma_raw * sigma_raw + sigma_floor * sigma_floor)
    sigma = np.maximum(sigma, np.maximum(np.nanmedian(sigma), np.nanmedian(q) * 1e-6))

    grid = np.linspace(float(icfg["e_min_C"]), float(icfg["e_max_C"]), int(icfg.get("grid_points", 900)))
    candidates: dict[tuple[int, ...], dict[str, Any]] = {}
    for initial_e in grid:
        candidate = _iterate_candidate(
            initial_e=float(initial_e),
            q=q,
            sigma=sigma,
            max_integer=int(icfg.get("max_integer", 80)),
            max_iterations=int(icfg.get("max_iterations", 8)),
            interval=(float(grid[0]), float(grid[-1])),
        )
        key = tuple(int(value) for value in candidate["n"].tolist())
        previous = candidates.get(key)
        if previous is None or candidate["chi2"] < previous["chi2"]:
            candidates[key] = candidate

    ordered = sorted(candidates.values(), key=lambda row: (row["chi2"], row["weighted_rms"]))
    best = ordered[0]
    n_hat = best["n"].astype(int)
    e_hat = float(best["e_C"])
    residual = q - n_hat * e_hat
    residual_sigma = residual / sigma
    flags: list[str] = []
    if best["weighted_rms"] > float(icfg.get("max_weighted_rms", 2.5)):
        flags.append("weighted_residual_too_large")
    if math.gcd(*[int(value) for value in n_hat.tolist()]) > 1:
        flags.append("integer_assignments_nonprimitive")
    if best["boundary_hit"]:
        flags.append("search_boundary_hit")
    if not best["converged"]:
        flags.append("integer_assignment_not_stable")
    if len(eligible) == min_records:
        flags.append("exploratory_small_sample")

    return {
        "reliable": len([flag for flag in flags if flag != "exploratory_small_sample"]) == 0,
        "status": "exploratory" if "exploratory_small_sample" in flags else ("reliable" if len(flags) == 0 else "diagnostic"),
        "e_hat_C": e_hat,
        "sigma_e_C": _estimate_sigma_e(n_hat, sigma),
        "weighted_rms": float(best["weighted_rms"]),
        "chi2": float(best["chi2"]),
        "num_used": len(eligible),
        "valid_q_count": len(eligible),
        "search_interval_C": [float(grid[0]), float(grid[-1])],
        "sigma_floor_C": sigma_floor,
        "converged": bool(best["converged"]),
        "boundary_hit": bool(best["boundary_hit"]),
        "assignments": [
            {
                "record_id": eligible[i]["record_id"],
                "q_C": float(q[i]),
                "sigma_q_C": float(sigma_raw[i]),
                "sigma_eff_C": float(sigma[i]),
                "n": int(n_hat[i]),
                "nearest_quantized_charge_C": float(n_hat[i] * e_hat),
                "residual_C": float(residual[i]),
                "residual_sigma": float(residual_sigma[i]),
            }
            for i in range(len(eligible))
        ],
        "candidates": [_public_candidate(row, q, sigma, eligible) for row in ordered[: int(icfg.get("candidate_count", 8))]],
        "charts": _charts(q, sigma_raw, n_hat, residual_sigma, e_hat),
        "plots_data": _charts(q, sigma_raw, n_hat, residual_sigma, e_hat),
        "quantized_alignment": {"model": "integer_multiple_weighted_residual", "weighted_rms": float(best["weighted_rms"])},
        "comparison": {
            "status": "not_computed",
            "reason": "No fitted continuous baseline is defined in Normal v1; the UI may show alignment diagnostics but must not claim model victory.",
        },
        "flags": flags,
    }


def _iterate_candidate(initial_e: float, q: np.ndarray, sigma: np.ndarray, max_integer: int, max_iterations: int, interval: tuple[float, float]) -> dict[str, Any]:
    e = initial_e
    previous: tuple[int, ...] | None = None
    converged = False
    boundary_hit = False
    n = np.ones_like(q, dtype=int)
    for iteration in range(max(1, max_iterations)):
        n = np.clip(np.rint(q / e), 1, max_integer).astype(int)
        key = tuple(int(value) for value in n.tolist())
        weights = 1.0 / np.square(sigma)
        denominator = float(np.sum(np.square(n) * weights))
        if denominator <= 0 or not math.isfinite(denominator):
            break
        e_next = float(np.sum(n * q * weights) / denominator)
        if e_next <= interval[0]:
            e_next = interval[0]
            boundary_hit = True
        elif e_next >= interval[1]:
            e_next = interval[1]
            boundary_hit = True
        if previous == key:
            converged = True
            e = e_next
            break
        previous = key
        e = e_next
        if iteration == max_iterations - 1:
            next_key = tuple(int(value) for value in np.clip(np.rint(q / e), 1, max_integer).astype(int).tolist())
            converged = next_key == key
    residual_sigma = (q - n * e) / sigma
    chi2 = float(np.sum(np.square(residual_sigma)))
    return {
        "e_C": float(e),
        "n": n,
        "chi2": chi2,
        "weighted_rms": math.sqrt(chi2 / len(q)),
        "converged": converged,
        "boundary_hit": boundary_hit,
    }


def _eligible_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for record in records:
        q = record.get("q") or {}
        charge = float(q.get("q_C") or q.get("charge_abs_C") or math.nan)
        sigma = float(q.get("sigma_q_C") or q.get("sigma_q_random_C") or math.nan)
        crossings = record.get("crossing_events") or []
        crossings_ok = all(event.get("review_result") == "same_drop" for event in crossings)
        if record.get("kept") and record.get("status") == "accepted" and crossings_ok and q.get("valid") and math.isfinite(charge) and charge > 0 and math.isfinite(sigma) and sigma > 0:
            out.append(record)
    return out


def _public_candidate(candidate: dict[str, Any], q: np.ndarray, sigma: np.ndarray, records: list[dict[str, Any]]) -> dict[str, Any]:
    n = candidate["n"].astype(int)
    e = float(candidate["e_C"])
    residual_sigma = (q - n * e) / sigma
    return {
        "e_C": e,
        "weighted_rms": float(candidate["weighted_rms"]),
        "chi2": float(candidate["chi2"]),
        "converged": bool(candidate["converged"]),
        "boundary_hit": bool(candidate["boundary_hit"]),
        "integer_assignment": [int(value) for value in n.tolist()],
        "residuals": [
            {
                "record_id": records[i]["record_id"],
                "n": int(n[i]),
                "residual_sigma": float(residual_sigma[i]),
            }
            for i in range(len(records))
        ],
    }


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
    }


def _estimate_sigma_e(n_hat: np.ndarray, sigma: np.ndarray) -> float | None:
    weights = 1.0 / np.square(sigma)
    denominator = float(np.sum(np.square(n_hat) * weights))
    if denominator <= 0 or not math.isfinite(denominator):
        return None
    sigma_e = math.sqrt(1.0 / denominator)
    return sigma_e if math.isfinite(sigma_e) and sigma_e > 0 else None
