from __future__ import annotations

import math
from functools import reduce
from typing import Any

import numpy as np

from millikan_ai.elementary.estimate import E_PRIOR_MAX_C, E_PRIOR_MIN_C, estimate_elementary_charge


def _usable_records(q_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable: list[dict[str, Any]] = []
    for record in q_records:
        if record.get("selected") is False:
            continue
        try:
            charge = float(record.get("q_C", record.get("charge_abs_C")))
            sigma = float(record.get("sigma_q_C", record.get("sigma_q_total_C")))
        except (TypeError, ValueError):
            continue
        if bool(record.get("usable_for_inversion", True)) and math.isfinite(charge) and charge > 0 and math.isfinite(sigma) and sigma > 0:
            usable.append({**record, "q_C": charge, "sigma_q_C": sigma})
    return usable


def _gcd(values: list[int]) -> int:
    return reduce(math.gcd, [abs(int(value)) for value in values], 0)


def estimate_normal_integer_fit(q_records: list[dict[str, Any]], *, grid_points: int = 1200) -> dict[str, Any]:
    usable = _usable_records(q_records)
    if len(usable) < 3:
        return {
            "valid": False,
            "status": "insufficient_q_records",
            "usable_q_count": len(usable),
            "flags": ["insufficient_q_records"],
        }
    charges = np.asarray([row["q_C"] for row in usable], dtype=float)
    sigmas = np.asarray([row["sigma_q_C"] for row in usable], dtype=float)
    e_grid = np.linspace(E_PRIOR_MIN_C, E_PRIOR_MAX_C, int(max(20, grid_points)))
    scores: list[float] = []
    assignments_by_index: list[np.ndarray] = []
    for e_value in e_grid:
        n = np.maximum(1, np.rint(charges / float(e_value)).astype(int))
        residual = (charges - n * float(e_value)) / sigmas
        scores.append(float(np.sum(np.square(residual))))
        assignments_by_index.append(n)
    score_arr = np.asarray(scores, dtype=float)
    best_index = int(np.argmin(score_arr))
    e_hat = float(e_grid[best_index])
    n_hat = assignments_by_index[best_index]
    residual_C = charges - n_hat * e_hat
    normalized = residual_C / sigmas
    grid_step = float(e_grid[1] - e_grid[0]) if len(e_grid) > 1 else E_PRIOR_MAX_C - E_PRIOR_MIN_C
    boundary_threshold = max(2.0 * grid_step, 0.02 * (E_PRIOR_MAX_C - E_PRIOR_MIN_C))
    boundary_hit = min(abs(e_hat - E_PRIOR_MIN_C), abs(E_PRIOR_MAX_C - e_hat)) <= boundary_threshold
    gcd_value = _gcd(n_hat.tolist())
    primitive = gcd_value <= 1
    intervals = e_grid[score_arr <= score_arr[best_index] + 3.84]
    if len(intervals):
        ci_low = float(intervals[0])
        ci_high = float(intervals[-1])
    else:
        ci_low = ci_high = e_hat
    sigma_e = abs(ci_high - ci_low) / (2.0 * 1.96) if ci_high > ci_low else 0.0
    loo_rows: list[dict[str, Any]] = []
    if len(usable) >= 4:
        for index, record in enumerate(usable):
            subset = [row for row_idx, row in enumerate(usable) if row_idx != index]
            sub = estimate_normal_integer_fit(subset, grid_points=min(240, grid_points))
            loo_rows.append(
                {
                    "record_id": record.get("record_id", f"q_{index+1:03d}"),
                    "valid": bool(sub.get("valid")),
                    "e_hat_C": sub.get("e_hat_C"),
                    "delta_from_full_C": (float(sub["e_hat_C"]) - e_hat) if sub.get("e_hat_C") else None,
                }
            )
    unstable = any(row.get("delta_from_full_C") is not None and abs(float(row["delta_from_full_C"])) > 0.08e-19 for row in loo_rows)
    rms = float(math.sqrt(np.mean(np.square(normalized))))
    flags: list[str] = []
    if boundary_hit:
        flags.append("prior_boundary_hit")
    if not primitive:
        flags.append("integer_assignments_nonprimitive")
    if unstable:
        flags.append("leave_one_out_unstable")
    if rms > 3.0:
        flags.append("large_weighted_residual")
    valid = not flags
    status = "success" if valid else flags[0]
    return {
        "valid": valid,
        "status": status,
        "flags": flags,
        "usable_q_count": len(usable),
        "e_hat_C": e_hat,
        "sigma_e_C": float(sigma_e),
        "ci_95_C": [ci_low, ci_high],
        "score": float(score_arr[best_index]),
        "weighted_residual_rms": rms,
        "search_interval_C": [E_PRIOR_MIN_C, E_PRIOR_MAX_C],
        "boundary_hit": bool(boundary_hit),
        "integer_gcd": int(gcd_value),
        "assignments": [
            {
                "record_id": usable[index].get("record_id", f"q_{index+1:03d}"),
                "q_C": float(charges[index]),
                "sigma_q_C": float(sigmas[index]),
                "n_i": int(n_hat[index]),
                "nearest_charge_C": float(n_hat[index] * e_hat),
                "residual_C": float(residual_C[index]),
                "normalized_residual": float(normalized[index]),
            }
            for index in range(len(usable))
        ],
        "profile": [
            {"e_C": float(e_grid[index]), "score": float(score_arr[index])}
            for index in np.linspace(0, len(e_grid) - 1, min(160, len(e_grid))).astype(int)
        ],
        "leave_one_out": loo_rows,
    }


def estimate_experimental_adapter(q_records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    usable = _usable_records(q_records)
    drops = []
    for index, record in enumerate(usable, start=1):
        drops.append(
            {
                "drop_id": record.get("record_id", f"q_{index:03d}"),
                "valid": True,
                "flags": [],
                "result": {
                    "charge_abs_C": float(record["q_C"]),
                    "sigma_charge_C": float(record["sigma_q_C"]),
                    "sigma_charge_random_C": float(record["sigma_q_C"]),
                },
            }
        )
    return estimate_elementary_charge(drops, config)


def estimate_both_algorithms(q_records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    normal = estimate_normal_integer_fit(q_records, grid_points=int(config.get("normal_mode", {}).get("integer_fit_grid_points", 1200)))
    experimental = estimate_experimental_adapter(q_records, config)
    usable_count = int(normal.get("usable_q_count", 0))
    return {
        "usable_q_count": usable_count,
        "normal_algorithm": normal,
        "experimental_algorithm": experimental,
        "reportable": bool(
            usable_count >= 3
            and (
                normal.get("valid") is True
                or experimental.get("fundamental_spacing_identified") is True
                or experimental.get("bounded_estimate_available") is True
            )
        ),
    }

