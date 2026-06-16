from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.special import logsumexp

from millikan_ai.elementary.estimate import _normal_logpdf


def build_elementary_plots_data(elementary: dict[str, Any], drop_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build frontend-neutral elementary-charge plotting data.

    The payload deliberately contains data, units, and chart semantics only. It
    does not encode renderer-specific colors, fonts, pixel sizes, or options.
    """

    assignments = _assignment_by_drop(elementary)
    observations = _observation_rows(drop_results, assignments)
    e_result = elementary.get("elementary_charge", {}) or {}
    comparison = elementary.get("model_comparison", {}) or {}
    e_hat = _finite_or_none(e_result.get("e_hat_C"))
    ci = _finite_pair(e_result.get("ci_95_C") or e_result.get("e_ci_95_C"))
    status = _plots_status(elementary, observations)
    reason = elementary.get("reason") or elementary.get("status") or ""

    charge_values = [row["q_C"] for row in observations if row.get("q_C") is not None]
    sigma_values = [row["sigma_q_C"] for row in observations if row.get("sigma_q_C") is not None]
    x_range = _charge_axis_range(charge_values, sigma_values, e_hat)
    quantized_levels = _quantized_levels(e_hat, x_range[1] if x_range else None)
    quantized_density = _quantized_density(e_result, x_range, sigma_values)
    continuous_density = _continuous_density(comparison, x_range, sigma_values)
    phase_points = _phase_points(observations)
    model_points = _model_comparison_points(comparison, observations)

    payload = {
        "schema_version": 2,
        "status": status,
        "reason": reason,
        "units": {
            "charge_primary": "1e-19 C",
            "charge_si": "C",
            "density": "relative_density",
            "residual": "C",
        },
        "summary": {
            "num_drops": len(observations),
            "e_hat_C": e_hat,
            "e_hat_1e_minus_19_C": _scale_charge(e_hat),
            "e_ci_95_C": ci,
            "e_ci_95_1e_minus_19_C": [_scale_charge(value) for value in ci] if ci else None,
            "fit_valid": _bool_or_none(elementary.get("fit_valid")),
            "bounded_estimate_available": _bool_or_none(elementary.get("bounded_estimate_available")),
            "quantization_favored": _bool_or_none(elementary.get("quantization_favored")),
            "quantization_supported": _bool_or_none(elementary.get("quantization_supported")),
            "fundamental_spacing_identified": _bool_or_none(elementary.get("fundamental_spacing_identified")),
            "status": elementary.get("status"),
            "delta_elpd": _finite_or_none(comparison.get("delta_elpd")),
            "evidence_label": comparison.get("evidence_label", "not_calibrated"),
        },
        "charts": {
            "charge_distribution": {
                "chart_id": "charge_distribution",
                "chart_type": "distribution_overlay",
                "title": "Charge distribution and model fit",
                "description": "Observed droplet charges with quantized and continuous predictive densities.",
                "units": {"x": "C", "x_display": "1e-19 C", "density": "relative_density"},
                "recommended_rendering": "rug_or_scatter_with_horizontal_error_bars_plus_density_curves",
                "x_axis": _axis("charge", x_range),
                "observations": observations,
                "histogram": _charge_histogram(charge_values),
                "quantized_density": quantized_density,
                "continuous_density": continuous_density,
                "quantized_levels": quantized_levels,
            },
            "integer_assignment": {
                "chart_id": "integer_assignment",
                "chart_type": "scatter_with_error_bars",
                "title": "Integer assignment comb",
                "description": "Each droplet charge compared with the nearest integer multiple of the bounded candidate.",
                "units": {"x": "integer n", "y": "C", "y_display": "1e-19 C"},
                "recommended_rendering": "scatter_with_vertical_error_bars_and_reference_levels",
                "points": _integer_assignment_points(observations),
                "reference_levels": quantized_levels,
                "e_hat_C": e_hat,
                "e_ci_95_C": ci,
            },
            "phase_residual": {
                "chart_id": "phase_residual",
                "chart_type": "scatter_and_histogram",
                "title": "Phase residual",
                "description": "Fractional residual q/e_hat - round(q/e_hat), centered so quantized data concentrate near zero.",
                "units": {"phase_residual": "unitless", "normalized_residual": "sigma"},
                "recommended_rendering": "scatter_by_integer_assignment_plus_phase_histogram",
                "points": phase_points,
                "histogram": _phase_histogram([row["phase_residual"] for row in phase_points if row.get("phase_residual") is not None]),
                "reference_lines": [{"value": 0.0, "label": "zero_residual"}],
                "uniform_reference_density": 1.0,
            },
            "model_comparison": {
                "chart_id": "model_comparison",
                "chart_type": "diverging_bar",
                "title": "Quantized vs continuous predictive score",
                "description": "Per-droplet log predictive density difference; positive values favor the quantized model.",
                "units": {"score": "log_predictive_density"},
                "recommended_rendering": "diverging_bar_with_total_delta",
                "status": "available" if model_points else "unavailable",
                "quantized_elpd": _finite_or_none(comparison.get("quantized_elpd")),
                "continuous_elpd": _finite_or_none(comparison.get("continuous_elpd")),
                "delta_elpd": _finite_or_none(comparison.get("delta_elpd")),
                "evidence_label": comparison.get("evidence_label", "not_calibrated"),
                "quantization_favored": _bool_or_none(comparison.get("quantization_favored")),
                "quantization_supported": _bool_or_none(comparison.get("quantization_supported")),
                "per_drop": model_points,
            },
        },
    }
    return _clean_json(payload)


def _assignment_by_drop(elementary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in elementary.get("drops", []) or []:
        drop_id = str(row.get("drop_id", ""))
        if drop_id:
            rows[drop_id] = row
    return rows


def _observation_rows(drop_results: list[dict[str, Any]], assignments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, drop in enumerate(drop_results, start=1):
        result = drop.get("result", {}) or {}
        q = _finite_or_none(result.get("charge_abs_C"))
        sigma = _finite_or_none(result.get("sigma_charge_total_C", result.get("sigma_charge_random_C", result.get("sigma_charge_C"))))
        if q is None:
            continue
        drop_id = str(drop.get("drop_id") or f"drop_{index:03d}")
        assignment = assignments.get(drop_id, {})
        n_hat = _int_or_none(assignment.get("n_hat"))
        nearest = _finite_or_none(assignment.get("nearest_quantized_charge_C"))
        residual = _finite_or_none(assignment.get("residual_C"))
        normalized = _finite_or_none(assignment.get("normalized_residual"))
        phase = _finite_or_none(assignment.get("phase_residual"))
        probability = _finite_or_none(assignment.get("assignment_probability_given_e", assignment.get("assignment_probability")))
        rows.append(
            {
                "drop_id": drop_id,
                "track_id": drop.get("track_id"),
                "q_C": q,
                "q_1e_minus_19_C": _scale_charge(q),
                "sigma_q_C": sigma,
                "sigma_q_1e_minus_19_C": _scale_charge(sigma),
                "n_hat": n_hat,
                "assignment_probability_given_e": probability,
                "used_in_estimation": bool(drop.get("valid")),
                "nearest_quantized_charge_C": nearest,
                "nearest_quantized_charge_1e_minus_19_C": _scale_charge(nearest),
                "residual_C": residual,
                "residual_1e_minus_19_C": _scale_charge(residual),
                "normalized_residual": normalized,
                "phase_residual": phase,
                "flags": list(drop.get("flags", []) or []),
            }
        )
    return rows


def _integer_assignment_points(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [
        "drop_id",
        "track_id",
        "q_C",
        "q_1e_minus_19_C",
        "sigma_q_C",
        "sigma_q_1e_minus_19_C",
        "n_hat",
        "nearest_quantized_charge_C",
        "nearest_quantized_charge_1e_minus_19_C",
        "residual_C",
        "residual_1e_minus_19_C",
        "normalized_residual",
        "assignment_probability_given_e",
        "flags",
    ]
    return [{key: row.get(key) for key in keys} for row in observations]


def _phase_points(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in observations:
        phase = row.get("phase_residual")
        if phase is None:
            continue
        rows.append(
            {
                "drop_id": row.get("drop_id"),
                "track_id": row.get("track_id"),
                "n_hat": row.get("n_hat"),
                "phase_residual": phase,
                "normalized_residual": row.get("normalized_residual"),
                "assignment_probability_given_e": row.get("assignment_probability_given_e"),
            }
        )
    return rows


def _model_comparison_points(comparison: dict[str, Any], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = comparison.get("per_observation_log_predictive_density", []) or []
    points = []
    for row in rows:
        index = _int_or_none(row.get("observation_index"))
        if index is None or index < 0 or index >= len(observations):
            continue
        observation = observations[index]
        points.append(
            {
                "drop_id": observation.get("drop_id"),
                "track_id": observation.get("track_id"),
                "fold_count": _int_or_none(row.get("split_count")),
                "quantized_log_predictive_density": _finite_or_none(row.get("quantized_log_predictive_density")),
                "continuous_log_predictive_density": _finite_or_none(row.get("continuous_log_predictive_density")),
                "delta_log_predictive_density": _finite_or_none(row.get("delta_log_predictive_density")),
            }
        )
    return points


def _charge_axis_range(charges: list[float], sigmas: list[float], e_hat: float | None) -> list[float] | None:
    if not charges:
        return None
    spread = max(sigmas) if sigmas else 0.05e-19
    low = max(0.0, min(charges) - 4.0 * spread)
    high = max(charges) + 4.0 * spread
    if e_hat is not None:
        low = min(low, 0.5 * e_hat)
        high = max(high, (math.ceil(high / e_hat) + 0.5) * e_hat)
    if high <= low:
        high = low + 1e-19
    return [float(low), float(high)]


def _axis(name: str, x_range: list[float] | None) -> dict[str, Any]:
    return {
        "field": name,
        "unit": "C",
        "display_unit": "1e-19 C",
        "recommended_range_C": x_range,
        "recommended_range_1e_minus_19_C": [_scale_charge(value) for value in x_range] if x_range else None,
    }


def _quantized_levels(e_hat: float | None, high: float | None) -> list[dict[str, Any]]:
    if e_hat is None or high is None or e_hat <= 0:
        return []
    nmax = max(1, int(math.ceil(high / e_hat)))
    return [{"n": int(n), "charge_C": float(n * e_hat), "charge_1e_minus_19_C": float(n * e_hat / 1e-19)} for n in range(1, nmax + 1)]


def _quantized_density(e_result: dict[str, Any], x_range: list[float] | None, sigmas: list[float]) -> list[dict[str, Any]]:
    e_hat = _finite_or_none(e_result.get("e_hat_C"))
    tau = _finite_or_none(e_result.get("tau_C"))
    lambda_decay = _finite_or_none(e_result.get("lambda_decay"))
    if x_range is None or e_hat is None or tau is None or lambda_decay is None or e_hat <= 0:
        return []
    x = np.linspace(x_range[0], x_range[1], 160)
    reference_sigma = _reference_sigma(sigmas)
    nmax = max(1, int(math.ceil(float(x_range[1]) / e_hat)) + 1)
    n_values = np.arange(1, nmax + 1, dtype=float)
    log_prior = -float(lambda_decay) * (n_values - 1.0)
    log_prior = log_prior - logsumexp(log_prior)
    sigma_total = math.sqrt(reference_sigma**2 + float(tau) ** 2)
    log_density = log_prior[None, :] + _normal_logpdf(x[:, None], n_values[None, :] * float(e_hat), np.full((len(x), nmax), sigma_total))
    density = np.exp(logsumexp(log_density, axis=1))
    return _density_points(x, density)


def _continuous_density(comparison: dict[str, Any], x_range: list[float] | None, sigmas: list[float]) -> list[dict[str, Any]]:
    model = comparison.get("continuous_density_model", {}) or {}
    weights = np.asarray(model.get("weights", []), dtype=float)
    means = np.asarray(model.get("means_C", []), dtype=float)
    variances = np.asarray(model.get("variances_C2", []), dtype=float)
    if x_range is None or len(weights) == 0 or len(weights) != len(means) or len(means) != len(variances):
        return []
    x = np.linspace(x_range[0], x_range[1], 160)
    reference_sigma = _reference_sigma(sigmas)
    total_sigma = np.sqrt(np.maximum(variances[None, :] + reference_sigma**2, 1e-60))
    log_density = np.log(weights[None, :]) + _normal_logpdf(x[:, None], means[None, :], total_sigma)
    density = np.exp(logsumexp(log_density, axis=1))
    return _density_points(x, density)


def _density_points(x: np.ndarray, density: np.ndarray) -> list[dict[str, Any]]:
    max_density = float(np.max(density)) if len(density) else 0.0
    if not math.isfinite(max_density) or max_density <= 0:
        return []
    relative = density / max_density
    return [
        {
            "x_C": float(x_value),
            "x_1e_minus_19_C": float(x_value / 1e-19),
            "density": float(value),
        }
        for x_value, value in zip(x.tolist(), relative.tolist())
    ]


def _charge_histogram(charges: list[float]) -> dict[str, Any]:
    if not charges:
        return {"bins": []}
    count = min(12, max(3, int(math.ceil(math.sqrt(len(charges))))))
    edges = np.histogram_bin_edges(np.asarray(charges, dtype=float), bins=count)
    counts, edges = np.histogram(np.asarray(charges, dtype=float), bins=edges)
    return {
        "bins": [
            {
                "bin_start_C": float(edges[index]),
                "bin_end_C": float(edges[index + 1]),
                "bin_start_1e_minus_19_C": float(edges[index] / 1e-19),
                "bin_end_1e_minus_19_C": float(edges[index + 1] / 1e-19),
                "count": int(counts[index]),
            }
            for index in range(len(counts))
        ]
    }


def _phase_histogram(phases: list[float]) -> dict[str, Any]:
    if not phases:
        return {"bins": []}
    edges = np.linspace(-0.5, 0.5, 11)
    counts, edges = np.histogram(np.asarray(phases, dtype=float), bins=edges)
    return {
        "bins": [
            {"bin_start": float(edges[index]), "bin_end": float(edges[index + 1]), "count": int(counts[index])}
            for index in range(len(counts))
        ]
    }


def _plots_status(elementary: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    if not observations or not elementary.get("bounded_estimate_available"):
        return "insufficient_data" if not elementary.get("bounded_estimate_available") else "partial"
    if elementary.get("fundamental_spacing_identified"):
        return "success"
    return "diagnostic" if elementary.get("bounded_estimate_available") else "partial"


def _reference_sigma(sigmas: list[float]) -> float:
    finite = [value for value in sigmas if math.isfinite(value) and value > 0]
    return float(np.median(finite)) if finite else 0.05e-19


def _finite_pair(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    low = _finite_or_none(value[0])
    high = _finite_or_none(value[1])
    if low is None or high is None:
        return None
    return [low, high]


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _scale_charge(value: float | None) -> float | None:
    return None if value is None else float(value / 1e-19)


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value
