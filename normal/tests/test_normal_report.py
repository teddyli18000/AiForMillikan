from millikan_ai.normal.session import render_report


def test_report_shows_concise_chinese_measurements_without_internal_payload():
    report = render_report(
        {
            "session_id": "internal-session-id",
            "records": [
                {
                    "record_id": "internal-record-id",
                    "status": "accepted",
                    "kept": True,
                    "video_path": r"C:\videos\drop.mp4",
                    "q": {"q_C": 1.6e-19, "sigma_q_C": 0.1e-19},
                }
            ],
            "inversion": {
                "status": "diagnostic",
                "e_hat_C": 1.602e-19,
                "sigma_e_C": 0.02e-19,
                "valid_q_count": 3,
                "flags": ["search_boundary_hit", "weighted_residual_too_large"],
                "weighted_rms": 0.2,
                "reference_comparison": {
                    "relative_uncertainty_percent": 1.2,
                    "percent_error_vs_reference": 0.01,
                    "reference_e_C": 1.602176634e-19,
                },
                "assignments": [{"record_id": "internal-record-id"}],
            },
        }
    )

    assert "# 密立根油滴实验记录" in report
    assert "| 测量序号 | 结果 | 电荷 q | 不确定度 σq | 视频 |" in report
    assert "| 1 | 已保留 | 1.6 × 10⁻¹⁹ C |" in report
    assert "drop.mp4" in report
    assert "σq 由速度拟合误差传播计算，未计仪器和物性参数误差。" in report
    assert "## 元电荷结果" in report
    assert "- 结果状态：需复核" in report
    assert "- 估计值：" in report
    assert "- 标准不确定度：" in report
    assert "- 诊断：估计值触及搜索范围边界" in report
    assert "- 诊断：电荷与整数倍的偏差较大" in report
    assert "与标准值的相对误差：0.01%（标准值 1.6022 × 10⁻¹⁹ C）" in report
    assert "| 1 | 已保留 | 是 |" not in report
    assert "internal-session-id" not in report
    assert "internal-record-id" not in report
    assert "Machine-readable" not in report
    assert "```json" not in report
    assert "weighted_rms" not in report


def test_report_translates_inversion_result_states():
    labels = {
        "reliable": "可靠候选",
        "exploratory": "样本较少",
        "diagnostic": "需复核",
        "insufficient_eligible_records": "记录不足",
    }
    for status, label in labels.items():
        report = render_report({"inversion": {"status": status, "flags": []}})
        assert f"结果状态：{label}" in report
