from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.special import logsumexp


@dataclass(frozen=True)
class QuantizedFit:
    e_C: float
    tau_C: float
    lambda_decay: float
    log_likelihood: float
    profile_e_C: np.ndarray
    profile_log_likelihood: np.ndarray


def _cfg_value(cfg: dict[str, Any], new_key: str, old_key: str | None, default: Any) -> Any:
    if new_key in cfg:
        return cfg[new_key]
    if old_key and old_key in cfg:
        return cfg[old_key]
    return default


def _usable_drops(drop_results: list[dict]) -> list[dict]:
    return [
        drop
        for drop in drop_results
        if drop.get("valid")
        and drop.get("result", {}).get("charge_abs_C") is not None
        and drop.get("result", {}).get("sigma_charge_C") is not None
    ]


def _normal_logpdf(x: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    return -0.5 * (np.log(2 * math.pi * sigma**2) + ((x - mean) / sigma) ** 2)


def _quantized_log_likelihood(
    charges: np.ndarray,
    sigmas: np.ndarray,
    e_C: float,
    tau_C: float,
    lambda_decay: float,
    nmax: int,
) -> float:
    n_values = np.arange(1, nmax + 1, dtype=float)
    log_prior = -float(lambda_decay) * (n_values - 1.0)
    log_prior = log_prior - logsumexp(log_prior)
    sigma_total = np.sqrt(np.square(sigmas[:, None]) + float(tau_C) ** 2)
    log_components = log_prior[None, :] + _normal_logpdf(charges[:, None], n_values[None, :] * float(e_C), sigma_total)
    return float(np.sum(logsumexp(log_components, axis=1)))


def _fit_quantized_profile(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any]) -> QuantizedFit:
    e_min = float(_cfg_value(cfg, "e_search_min_C", "e_min_C", 0.5e-19))
    e_max = float(_cfg_value(cfg, "e_search_max_C", "e_max_C", 2.5e-19))
    grid_points = int(_cfg_value(cfg, "profile_grid_points", "grid_points", 800))
    if not (0 < e_min < e_max) or grid_points < 10:
        raise ValueError("invalid_elementary_search_config")
    e_grid = np.linspace(e_min, e_max, grid_points)
    nmax = max(1, int(math.ceil(float(np.max(charges)) / e_min)) + 1)
    median_sigma = float(np.median(sigmas))
    tau_grid = np.array([0.0, 0.5, 1.0, 2.0, 4.0], dtype=float) * max(median_sigma, 1e-30)
    lambda_grid = np.array([0.0, 0.25, 0.75, 1.5, 3.0], dtype=float)
    best: tuple[float, float, float, float] | None = None
    profile = []
    for e_C in e_grid:
        best_for_e: tuple[float, float, float] | None = None
        for tau_C in tau_grid:
            for lambda_decay in lambda_grid:
                ll = _quantized_log_likelihood(charges, sigmas, float(e_C), float(tau_C), float(lambda_decay), nmax)
                if best_for_e is None or ll > best_for_e[0]:
                    best_for_e = (ll, float(tau_C), float(lambda_decay))
        assert best_for_e is not None
        profile.append(best_for_e[0])
        if best is None or best_for_e[0] > best[0]:
            best = (best_for_e[0], float(e_C), best_for_e[1], best_for_e[2])
    assert best is not None
    return QuantizedFit(
        e_C=best[1],
        tau_C=best[2],
        lambda_decay=best[3],
        log_likelihood=best[0],
        profile_e_C=e_grid,
        profile_log_likelihood=np.asarray(profile, dtype=float),
    )


def _assignment_rows(charges: np.ndarray, sigmas: np.ndarray, fit: QuantizedFit, drops: list[dict]) -> list[dict[str, object]]:
    nmax = max(1, int(math.ceil(float(np.max(charges)) / fit.e_C)) + 2)
    n_values = np.arange(1, nmax + 1, dtype=float)
    log_prior = -fit.lambda_decay * (n_values - 1.0)
    log_prior = log_prior - logsumexp(log_prior)
    sigma_total = np.sqrt(np.square(sigmas[:, None]) + fit.tau_C**2)
    log_post = log_prior[None, :] + _normal_logpdf(charges[:, None], n_values[None, :] * fit.e_C, sigma_total)
    log_post = log_post - logsumexp(log_post, axis=1)[:, None]
    probabilities = np.exp(log_post)
    n_hat = np.argmax(probabilities, axis=1) + 1
    rows = []
    for i, n_i in enumerate(n_hat):
        nearest = float(n_i * fit.e_C)
        residual = float(charges[i] - nearest)
        rows.append(
            {
                "drop_id": drops[i].get("drop_id", f"drop_{i+1:03d}"),
                "charge_C": float(charges[i]),
                "sigma_charge_C": float(sigmas[i]),
                "n_hat": int(n_i),
                "assignment_probability": float(probabilities[i, n_i - 1]),
                "nearest_quantized_charge_C": nearest,
                "residual_C": residual,
                "normalized_residual": float(residual / max(sigmas[i], 1e-30)),
                "phase_residual": float((charges[i] / fit.e_C) - round(charges[i] / fit.e_C)),
            }
        )
    return rows


def _candidate_modes(fit: QuantizedFit) -> list[dict[str, float]]:
    e_grid = fit.profile_e_C
    profile = fit.profile_log_likelihood
    max_ll = float(np.max(profile))
    indices: set[int] = set()
    for idx in range(1, len(profile) - 1):
        if profile[idx] >= profile[idx - 1] and profile[idx] >= profile[idx + 1]:
            indices.add(idx)
    for target in (fit.e_C / 2.0, fit.e_C * 2.0):
        if e_grid[0] <= target <= e_grid[-1]:
            indices.add(int(np.argmin(np.abs(e_grid - target))))
    indices.add(int(np.argmax(profile)))
    modes = []
    for idx in sorted(indices, key=lambda item: profile[item], reverse=True):
        relative = float(math.exp(min(0.0, float(profile[idx] - max_ll))))
        if relative >= 1e-4:
            modes.append({"e_C": float(e_grid[idx]), "relative_likelihood": relative})
    unique: list[dict[str, float]] = []
    for mode in modes:
        if not any(abs(mode["e_C"] - existing["e_C"]) <= (e_grid[1] - e_grid[0]) * 2 for existing in unique):
            unique.append(mode)
    return unique[:8]


def _profile_interval(fit: QuantizedFit) -> list[float]:
    threshold = fit.log_likelihood - 0.5 * 1.96**2
    mask = fit.profile_log_likelihood >= threshold
    if not np.any(mask):
        return [fit.e_C, fit.e_C]
    return [float(np.min(fit.profile_e_C[mask])), float(np.max(fit.profile_e_C[mask]))]


def _fit_gmm(values: np.ndarray, max_components: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    best: dict[str, Any] | None = None
    values = np.asarray(values, dtype=float)
    n = len(values)
    variance_floor = max(float(np.var(values)) * 1e-4, 1e-60)
    for k in range(1, max(1, max_components) + 1):
        if k == 1:
            weights = np.array([1.0])
            means = np.array([float(np.mean(values))])
            variances = np.array([max(float(np.var(values)), variance_floor)])
        else:
            quantiles = np.linspace(0.1, 0.9, k)
            means = np.quantile(values, quantiles)
            means = means + rng.normal(0.0, math.sqrt(variance_floor), size=k)
            variances = np.full(k, max(float(np.var(values)), variance_floor))
            weights = np.full(k, 1.0 / k)
            for _ in range(80):
                sigma = np.sqrt(variances)
                log_resp = np.log(weights[None, :]) + _normal_logpdf(values[:, None], means[None, :], sigma[None, :])
                log_norm = logsumexp(log_resp, axis=1)
                resp = np.exp(log_resp - log_norm[:, None])
                nk = np.maximum(resp.sum(axis=0), 1e-12)
                weights = nk / n
                means = (resp * values[:, None]).sum(axis=0) / nk
                variances = np.maximum((resp * np.square(values[:, None] - means[None, :])).sum(axis=0) / nk, variance_floor)
        ll = _continuous_log_likelihood(values, np.zeros_like(values), {"weights": weights, "means": means, "variances": variances})
        params = 3 * k - 1
        bic = -2 * ll + params * math.log(max(n, 2))
        model = {"weights": weights, "means": means, "variances": variances, "components": k, "log_likelihood": ll, "bic": bic}
        if best is None or bic < best["bic"]:
            best = model
    assert best is not None
    return best


def _continuous_log_likelihood(charges: np.ndarray, sigmas: np.ndarray, model: dict[str, Any]) -> float:
    weights = np.asarray(model["weights"], dtype=float)
    means = np.asarray(model["means"], dtype=float)
    variances = np.asarray(model["variances"], dtype=float)
    total_sigma = np.sqrt(variances[None, :] + np.square(sigmas[:, None]))
    log_components = np.log(weights[None, :]) + _normal_logpdf(charges[:, None], means[None, :], total_sigma)
    return float(np.sum(logsumexp(log_components, axis=1)))


def _predictive_model_comparison(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any]) -> dict[str, object]:
    if len(charges) < 3:
        return {
            "continuous_model": "error_convolved_gmm",
            "comparison_method": "insufficient_drops",
            "quantized_elpd": math.nan,
            "continuous_elpd": math.nan,
            "delta_elpd": math.nan,
            "evidence_label": "insufficient",
        }
    seed = int(cfg.get("random_seed", 42))
    quantized_scores = []
    continuous_scores = []
    for held_out in range(len(charges)):
        mask = np.ones(len(charges), dtype=bool)
        mask[held_out] = False
        train_charges = charges[mask]
        train_sigmas = sigmas[mask]
        test_charge = charges[~mask]
        test_sigma = sigmas[~mask]
        q_fit = _fit_quantized_profile(train_charges, train_sigmas, cfg)
        e_min = float(_cfg_value(cfg, "e_search_min_C", "e_min_C", 0.5e-19))
        nmax = max(1, int(math.ceil(float(max(np.max(train_charges), np.max(test_charge))) / e_min)) + 1)
        quantized_scores.append(
            _quantized_log_likelihood(test_charge, test_sigma, q_fit.e_C, q_fit.tau_C, q_fit.lambda_decay, nmax)
        )
        max_components = min(4, max(1, len(train_charges) // 3))
        c_model = _fit_gmm(train_charges, max_components=max_components, seed=seed + held_out)
        continuous_scores.append(_continuous_log_likelihood(test_charge, test_sigma, c_model))
    quantized_elpd = float(np.sum(quantized_scores))
    continuous_elpd = float(np.sum(continuous_scores))
    delta = quantized_elpd - continuous_elpd
    if delta > 5.0:
        label = "strong"
    elif delta > 2.0:
        label = "moderate"
    elif delta > 0.0:
        label = "weak"
    else:
        label = "insufficient"
    final_model = _fit_gmm(charges, max_components=min(4, max(1, len(charges) // 3)), seed=seed)
    return {
        "continuous_model": "error_convolved_gmm",
        "continuous_components": int(final_model["components"]),
        "comparison_method": "leave_one_out_predictive_likelihood" if len(charges) < 20 else "leave_one_out_predictive_likelihood",
        "quantized_elpd": quantized_elpd,
        "continuous_elpd": continuous_elpd,
        "delta_elpd": delta,
        "evidence_label": label,
    }


def _bootstrap_e(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any]) -> list[float]:
    samples = int(_cfg_value(cfg, "e_bootstrap_samples", "bootstrap_samples", 0))
    if samples <= 0:
        return []
    rng = random.Random(int(cfg.get("random_seed", 42)))
    boot = []
    for _ in range(samples):
        indices = [rng.randrange(len(charges)) for _ in range(len(charges))]
        try:
            sample_fit = _fit_quantized_profile(charges[indices], sigmas[indices], cfg)
            boot.append(float(sample_fit.e_C))
        except ValueError:
            continue
    return boot


def estimate_elementary_charge(drop_results: list[dict], config: dict) -> dict[str, object]:
    cfg = config["elementary"]
    valid = _usable_drops(drop_results)
    min_drops = int(_cfg_value(cfg, "min_drops_for_estimation", "min_drops", 3))
    if len(valid) == 1:
        return {
            "valid": False,
            "flags": ["insufficient_independent_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": 1,
            "reason": "Blind elementary-charge estimation requires multiple independent q_i values.",
        }
    if len(valid) < min_drops:
        return {
            "valid": False,
            "flags": ["insufficient_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": len(valid),
        }
    charges = np.array([float(drop["result"]["charge_abs_C"]) for drop in valid], dtype=float)
    sigmas = np.array([float(drop["result"]["sigma_charge_C"]) for drop in valid], dtype=float)
    finite = np.isfinite(charges) & np.isfinite(sigmas) & (charges > 0) & (sigmas >= 0)
    charges = charges[finite]
    sigmas = sigmas[finite]
    valid = [drop for drop, keep in zip(valid, finite.tolist()) if keep]
    if len(valid) < min_drops:
        return {
            "valid": False,
            "flags": ["insufficient_finite_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": len(valid),
        }
    positive_sigmas = sigmas[sigmas > 0]
    numerical_floor = max(float(np.median(positive_sigmas)) * 1e-6, 1e-30) if len(positive_sigmas) else 1e-30
    sigmas = np.maximum(sigmas, numerical_floor)
    fit = _fit_quantized_profile(charges, sigmas, cfg)
    assignments = _assignment_rows(charges, sigmas, fit, valid)
    modes = _candidate_modes(fit)
    harmonic = any(
        mode["relative_likelihood"] >= 0.02
        and (abs(mode["e_C"] - fit.e_C / 2.0) / fit.e_C < 0.08 or abs(mode["e_C"] - fit.e_C * 2.0) / fit.e_C < 0.08)
        for mode in modes
    )
    boot = _bootstrap_e(charges, sigmas, cfg)
    ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))] if boot else [fit.e_C, fit.e_C]
    e_min = float(_cfg_value(cfg, "e_search_min_C", "e_min_C", 0.5e-19))
    e_max = float(_cfg_value(cfg, "e_search_max_C", "e_max_C", 2.5e-19))
    comparison = _predictive_model_comparison(charges, sigmas, cfg)
    return {
        "valid": True,
        "num_total_drops": len(drop_results),
        "num_used_drops": len(valid),
        "elementary_charge": {
            "e_hat_C": float(fit.e_C),
            "e_hat_1e_minus_19_C": float(fit.e_C / 1e-19),
            "sigma_e_C": float(np.std(boot, ddof=1)) if len(boot) > 1 else 0.0,
            "ci_95_C": ci,
            "profile_ci_95_C": _profile_interval(fit),
            "search_interval_C": [e_min, e_max],
            "blind_estimation": "bounded_interval_no_reference_e_input",
            "tau_C": float(fit.tau_C),
            "lambda_decay": float(fit.lambda_decay),
        },
        "drops": assignments,
        "harmonic_analysis": {
            "harmonic_ambiguity": bool(harmonic),
            "candidate_modes": modes,
        },
        "model_comparison": {
            "weighted_residual_rms_C": float(
                math.sqrt(np.mean([row["residual_C"] ** 2 for row in assignments]))
            ),
            "method": "bounded_profile_quantized_likelihood",
            "log_likelihood": float(fit.log_likelihood),
            **comparison,
        },
        "flags": ["harmonic_ambiguity"] if harmonic else [],
    }
