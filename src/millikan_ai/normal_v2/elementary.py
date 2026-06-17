from __future__ import annotations

import math
from typing import Any

import numpy as np

E_MIN_C = 1.35e-19
E_MAX_C = 1.90e-19


def estimate_normal_integer_fit(q_records: list[dict[str, Any]], *, grid_points: int = 1200) -> dict[str, Any]:
    usable = []
    for row in q_records:
        if not row.get("valid") or not row.get("selected", True):
            continue
        try:
            q = float(row.get("q_C"))
            sigma = float(row.get("sigma_q_C"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(q) and q > 0 and math.isfinite(sigma) and sigma > 0:
            usable.append((str(row.get("record_id", f"q_{len(usable)+1}")), q, sigma))
    if len(usable) < 3:
        return {"valid": False, "status": "insufficient_selected_valid_q", "flags": ["insufficient_selected_valid_q"], "usable_q_count": len(usable)}

    charges = np.asarray([item[1] for item in usable], dtype=float)
    sigmas = np.asarray([item[2] for item in usable], dtype=float)
    grid = np.linspace(E_MIN_C, E_MAX_C, max(50, int(grid_points)))
    scores = []
    assignments = []
    for e in grid:
        n = np.maximum(1, np.rint(charges / e)).astype(int)
        residual = (charges - n * e) / sigmas
        scores.append(float(np.sum(residual**2)))
        assignments.append(n)
    best_idx = int(np.argmin(scores))
    e_hat = float(grid[best_idx])
    n_hat = assignments[best_idx]
    residual_C = charges - n_hat * e_hat
    normalized = residual_C / sigmas
    flags: list[str] = []

    boundary_margin = 0.01 * (E_MAX_C - E_MIN_C)
    if e_hat <= E_MIN_C + boundary_margin or e_hat >= E_MAX_C - boundary_margin:
        flags.append("search_boundary_hit")
    gcd_value = _gcd([int(value) for value in n_hat.tolist()])
    if gcd_value > 1:
        flags.append("integer_assignments_nonprimitive")
    rms = float(math.sqrt(np.mean(normalized**2)))
    if rms > 3.0:
        flags.append("weighted_residual_too_large")
    if len(usable) >= 4:
        loo = []
        for index in range(len(usable)):
            subset = [row for idx, row in enumerate(q_records) if idx != index]
            sub = estimate_normal_integer_fit(subset, grid_points=min(240, grid_points))
            if sub.get("valid") and abs(float(sub["e_hat_C"]) - e_hat) / e_hat > 0.08:
                flags.append("leave_one_out_unstable")
                break
            loo.append(sub.get("e_hat_C"))
    candidate_half = e_hat / 2.0
    candidate_double = e_hat * 2.0
    if E_MIN_C <= candidate_half <= E_MAX_C or E_MIN_C <= candidate_double <= E_MAX_C:
        # Diagnostic only unless another guard fails; surface for UI/report.
        harmonic_warning = True
    else:
        harmonic_warning = False

    return {
        "valid": not flags,
        "status": "ok" if not flags else flags[0],
        "flags": flags,
        "usable_q_count": len(usable),
        "e_hat_C": e_hat,
        "weighted_residual_rms": rms,
        "integer_gcd": gcd_value,
        "harmonic_warning": harmonic_warning,
        "drops": [
            {
                "record_id": usable[index][0],
                "q_C": float(charges[index]),
                "sigma_q_C": float(sigmas[index]),
                "n_hat": int(n_hat[index]),
                "nearest_charge_C": float(n_hat[index] * e_hat),
                "residual_C": float(residual_C[index]),
                "normalized_residual": float(normalized[index]),
            }
            for index in range(len(usable))
        ],
        "profile": [{"e_C": float(e), "score": float(score)} for e, score in zip(grid, scores)],
    }


def _gcd(values: list[int]) -> int:
    current = 0
    for value in values:
        current = math.gcd(current, abs(int(value)))
    return current

