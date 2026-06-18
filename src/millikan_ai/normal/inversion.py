from __future__ import annotations

import math
from typing import Any

import numpy as np

from millikan_ai.elementary.estimate import estimate_elementary_charge


def run_weighted_integer_inversion(records: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    icfg = cfg["inversion"]
    selected = _eligible(records)
    if len(selected) < int(icfg.get("min_records", 3)):
        return {"reliable": False, "status": "insufficient_eligible_records", "num_used": len(selected), "flags": ["insufficient_eligible_records"]}
    q = np.array([float(row["q"]["charge_abs_C"]) for row in selected], dtype=float)
    sigma = np.array([float(row["q"]["sigma_q_total_C"]) for row in selected], dtype=float)
    e_grid = np.linspace(float(icfg["e_min_C"]), float(icfg["e_max_C"]), int(icfg.get("grid_points", 900)))
    best = None
    profile = []
    max_integer = int(icfg.get("max_integer", 60))
    for e in e_grid:
        n = np.clip(np.rint(q / e), 1, max_integer)
        residual = np.sum(((q - n * e) / sigma) ** 2)
        profile.append(float(residual))
        if best is None or residual < best[0]:
            best = (float(residual), float(e), n.astype(int))
    assert best is not None
    rms = math.sqrt(best[0] / len(q))
    flags: list[str] = []
    if rms > float(icfg.get("max_weighted_rms", 2.5)):
        flags.append("weighted_residual_too_large")
    if math.gcd(*[int(x) for x in best[2].tolist()]) > 1:
        flags.append("integer_assignments_nonprimitive")
    if _harmonic_ambiguous(e_grid, np.asarray(profile), best[1], float(icfg.get("harmonic_tolerance", 0.04))):
        flags.append("harmonic_ambiguity")
    loo = _leave_one_out(q, sigma, icfg, best[1])
    if any(abs(row["relative_shift"]) > float(icfg.get("leave_one_out_max_rel_shift", 0.08)) for row in loo if row["valid"]):
        flags.append("leave_one_out_unstable")
    return {
        "reliable": len(flags) == 0,
        "status": "reliable" if len(flags) == 0 else "unreliable",
        "e_hat_C": best[1],
        "weighted_rms": rms,
        "num_used": len(selected),
        "assignments": [
            {"record_id": selected[i]["record_id"], "q_C": float(q[i]), "sigma_q_C": float(sigma[i]), "n": int(best[2][i]), "residual_sigma": float((q[i] - best[2][i] * best[1]) / sigma[i])}
            for i in range(len(selected))
        ],
        "leave_one_out": loo,
        "flags": flags,
    }


def run_experimental_adapter(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    drops = []
    for row in _eligible(records):
        drops.append({
            "drop_id": row["record_id"],
            "valid": True,
            "result": {
                "charge_abs_C": row["q"]["charge_abs_C"],
                "sigma_charge_C": row["q"]["sigma_q_total_C"],
            },
        })
    if len(drops) < 3:
        return {"reliable": False, "status": "insufficient_eligible_records", "num_used": len(drops)}
    cfg = {"elementary": dict(config.get("elementary", {}))}
    cfg["elementary"].setdefault("e_bootstrap_samples", 100)
    cfg["elementary"].setdefault("measurement_mc_samples", 100)
    cfg["elementary"].setdefault("null_simulation_samples", 0)
    result = estimate_elementary_charge(drops, cfg)
    return {
        "reliable": bool(result.get("fundamental_spacing_identified")),
        "status": result.get("status"),
        "num_used": result.get("num_used_drops"),
        "result": result,
    }


def _eligible(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in records:
        q = row.get("q") or {}
        if row.get("selected") and row.get("status") == "valid" and q.get("valid") and not q.get("diagnostic_only"):
            sigma = float(q.get("sigma_q_total_C") or math.nan)
            charge = float(q.get("charge_abs_C") or math.nan)
            if math.isfinite(charge) and charge > 0 and math.isfinite(sigma) and sigma > 0:
                out.append(row)
    return out


def _harmonic_ambiguous(e_grid: np.ndarray, profile: np.ndarray, e_hat: float, tolerance: float) -> bool:
    best = float(np.min(profile))
    for divisor in [2, 3]:
        target = e_hat / divisor
        if e_grid[0] <= target <= e_grid[-1]:
            idx = int(np.argmin(np.abs(e_grid - target)))
            if profile[idx] <= best * (1.0 + tolerance):
                return True
    return False


def _leave_one_out(q: np.ndarray, sigma: np.ndarray, cfg: dict[str, Any], e_hat: float) -> list[dict[str, Any]]:
    if len(q) < 4:
        return []
    rows = []
    for idx in range(len(q)):
        mask = np.ones(len(q), dtype=bool)
        mask[idx] = False
        sub_records = [{"record_id": str(i), "selected": True, "status": "valid", "q": {"valid": True, "charge_abs_C": float(q[i]), "sigma_q_total_C": float(sigma[i])}} for i in np.where(mask)[0]]
        result = run_weighted_integer_inversion(sub_records, {"inversion": cfg})
        value = result.get("e_hat_C")
        rows.append({"index": int(idx), "valid": value is not None, "e_hat_C": value, "relative_shift": float((value - e_hat) / e_hat) if value else math.nan})
    return rows

