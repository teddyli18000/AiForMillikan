from scripts.validate_estimator_simulation import run_simulation


def test_estimator_simulation_script_smoke_runs_small_case():
    result = run_simulation("configs/default.yaml", replicates=1, seed=123, profile_points=40, null_samples=0, n_values=(10,), noise_values=(0.06,))

    assert {
        "fit_valid_rate",
        "bounded_estimate_available_rate",
        "fundamental_spacing_identified_rate",
        "search_boundary_hit_rate",
        "profile_optimization_incomplete_rate",
        "primitive_assignment_failure_rate",
        "catastrophic_error_rate",
        "continuous_quantization_favored_rate",
        "continuous_quantization_supported_rate",
        "continuous_false_fundamental_identification_rate",
    }.issubset(result["summary"])
    assert result["summary"]["quantized_valid_count"] > 0
    assert len(result["quantized"]) == 1
    assert len(result["continuous"]) == 1
    assert "difficult_cases" in result
    assert result["difficult_cases"]
