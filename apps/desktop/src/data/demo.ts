import type { AnalysisResponse, RunArtifacts, VideoMetadata } from "../types";

export const demoMetadata: VideoMetadata = {
  path: "raw_data/2.mp4",
  readable: true,
  width: 1280,
  height: 720,
  fps: 30,
  frame_count: 542,
  duration_s: 18.06
};

export const demoArtifacts: RunArtifacts = {
  run_dir: "runs/demo_millikan",
  manifest: {
    schema_version: 1,
    run_dir: "runs/demo_millikan",
    status: {
      video_readable: true,
      valid_for_q: true,
      valid_for_elementary_charge: false,
      elementary_estimation_ready: true,
      bounded_estimate_available: true,
      quantization_supported: null,
      elementary_status: "bounded_estimate_evidence_not_calibrated",
      flags: ["evidence_not_calibrated"]
    },
    counts: {
      platforms: 3,
      drops: 12,
      valid_drops: 7,
      quality_kept_drops: 7,
      track_rows: 186,
      segments: 3
    },
    video: demoMetadata,
    files: {
      diagnostic_overlay_jpg: "",
      overlay_mp4: "",
      plots_data_json: "plots_data.json"
    }
  },
  validity_report: {
    overall_valid_for_q: true,
    overall_valid_for_elementary_charge: false,
    elementary_estimation_ready: true,
    bounded_estimate_available: true,
    quantization_supported: null,
    elementary_status: "bounded_estimate_evidence_not_calibrated",
    combined_flags: ["evidence_not_calibrated"],
    blocking_failed_checks: [],
    checks: [
      { id: "video_readable", passed: true, message: "Video can be opened by OpenCV." },
      { id: "scale_calibrated", passed: true, message: "Grid distance calibration produced scale_y_m_per_px." },
      { id: "drop_q_valid", passed: true, message: "Physics q calculation is valid." },
      { id: "elementary_fundamental_spacing_identified", passed: false, message: "Final elementary-charge conclusion requires calibrated quantization support." }
    ]
  },
  elementary_charge_result: {
    valid: true,
    fit_valid: true,
    bounded_estimate_available: true,
    quantization_favored: true,
    quantization_supported: null,
    primitive_assignment_supported: true,
    fundamental_spacing_identified: false,
    status: "bounded_estimate_evidence_not_calibrated",
    reason: "Evidence labels are not calibrated; treat this as a diagnostic candidate.",
    flags: ["evidence_not_calibrated"],
    num_used_drops: 7,
    elementary_charge: {
      e_hat_C: 1.604e-19,
      sigma_e_C: 0.044e-19,
      ci_95_C: [1.531e-19, 1.684e-19],
      profile_ci_95_C: [1.552e-19, 1.671e-19],
      search_interval_C: [1.35e-19, 1.9e-19]
    }
  },
  model_comparison: {
    delta_elpd: 5.82,
    evidence_label: "not_calibrated",
    quantized_elpd: -13.8,
    continuous_elpd: -19.62
  },
  uncertainty_details: {
    status: "partial",
    random_uncertainty: "per-drop random q uncertainty uses joint alpha-gamma Monte Carlo",
    systematic_uncertainty: "shared systematic Monte Carlo not configured"
  },
  visualization_layers: {
    frame: {
      width: 1280,
      height: 720,
      fps: 30,
      frame_count: 542,
      duration_s: 18.06
    },
    coordinate_system: {
      origin: "top_left_video_pixel",
      x_positive: "right",
      y_positive: "down"
    },
    layers: [
      { id: "microscope_roi", type: "rect", x: 120, y: 80, w: 920, h: 560, label: "Microscope ROI" },
      { id: "tracking_roi", type: "rect", x: 180, y: 88, w: 760, h: 510, label: "Tracking ROI" },
      { id: "horizontal_grid_lines", type: "line_set", orientation: "horizontal", positions_px: [120, 206, 292, 378, 464, 550] },
      { id: "vertical_grid_lines", type: "line_set", orientation: "vertical", positions_px: [230, 360, 490, 620, 750, 880] },
      {
        id: "drop_tracks",
        type: "multi_frame_point_series",
        tracks: [
          {
            track_id: "candidate_001",
            drop_id: "drop_001",
            quality_score: 0.86,
            keep: true,
            q_valid: true,
            reject_reasons: "",
            points: [
              { frame_idx: 0, x_px: 318, y_px: 156, valid: true },
              { frame_idx: 60, x_px: 324, y_px: 220, valid: true },
              { frame_idx: 120, x_px: 331, y_px: 302, valid: true },
              { frame_idx: 180, x_px: 338, y_px: 384, valid: true },
              { frame_idx: 240, x_px: 344, y_px: 450, valid: true }
            ]
          },
          {
            track_id: "candidate_006",
            drop_id: "drop_006",
            quality_score: 0.74,
            keep: true,
            q_valid: true,
            reject_reasons: "",
            points: [
              { frame_idx: 0, x_px: 612, y_px: 182, valid: true },
              { frame_idx: 60, x_px: 618, y_px: 246, valid: true },
              { frame_idx: 120, x_px: 625, y_px: 304, valid: true },
              { frame_idx: 180, x_px: 632, y_px: 370, valid: true },
              { frame_idx: 240, x_px: 640, y_px: 432, valid: true }
            ]
          }
        ]
      }
    ]
  },
  plots_data: {
    schema_version: 2,
    status: "diagnostic",
    summary: {
      quantization_favored: true,
      quantization_supported: null,
      fundamental_spacing_identified: false
    },
    charts: {
      charge_distribution: {
        observations: [3.21, 4.82, 6.42, 8.03, 9.62, 11.23, 12.85].map((value, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          q_C: value * 1e-19,
          sigma_q_C: (0.11 + index * 0.01) * 1e-19,
          n_hat: Math.round(value / 1.604),
          assignment_probability_given_e: 0.78 + (index % 3) * 0.06
        })),
        quantized_density: Array.from({ length: 32 }, (_, index) => {
          const x = (2.4 + index * 0.36) * 1e-19;
          return { q_C: x, density: 0.55 + 0.42 * Math.sin(index * 0.82) ** 2 };
        }),
        continuous_density: Array.from({ length: 32 }, (_, index) => {
          const x = (2.4 + index * 0.36) * 1e-19;
          return { q_C: x, density: 0.35 + 0.3 * Math.cos(index * 0.35) ** 2 };
        }),
        quantized_levels: [1, 2, 3, 4, 5, 6, 7, 8].map((n) => ({ n, charge_C: n * 1.604e-19 }))
      },
      integer_assignment: {
        points: [3.21, 4.82, 6.42, 8.03, 9.62, 11.23, 12.85].map((value, index) => {
          const n = Math.round(value / 1.604);
          return {
            drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
            q_C: value * 1e-19,
            n_hat: n,
            nearest_quantized_charge_C: n * 1.604e-19,
            residual_C: (value - n * 1.604) * 1e-19,
            normalized_residual: [-0.18, 0.07, 0.14, -0.02, -0.21, 0.11, 0.19][index],
            assignment_probability_given_e: 0.8 + (index % 3) * 0.05
          };
        })
      },
      phase_residual: {
        points: [-0.018, 0.006, 0.021, -0.004, -0.026, 0.012, 0.018].map((phase, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          phase_residual: phase,
          n_hat: index + 2
        }))
      },
      model_comparison: {
        delta_elpd: 5.82,
        quantized_elpd: -13.8,
        continuous_elpd: -19.62,
        per_drop: [0.72, 0.88, 0.31, 1.2, 0.66, 1.03, 1.02].map((value, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          delta_log_predictive_density: value
        }))
      }
    }
  },
  tables: {
    platforms: [
      { platform_id: "P001", start_frame: 0, end_frame: 156, voltage_V: 0, source: "auto_boundary_manual_voltage" },
      { platform_id: "P002", start_frame: 166, end_frame: 344, voltage_V: 239, source: "auto_boundary_manual_voltage" },
      { platform_id: "P003", start_frame: 355, end_frame: 542, voltage_V: 362, source: "auto_boundary_manual_voltage" }
    ],
    candidate_tracks_summary: [
      { rank: 1, candidate_id: "candidate_001", score_total: 0.91, q_valid: true, charge_abs_C: 3.21e-19, reject_reason: "" },
      { rank: 2, candidate_id: "candidate_006", score_total: 0.84, q_valid: true, charge_abs_C: 9.62e-19, reject_reason: "" },
      { rank: 3, candidate_id: "candidate_011", score_total: 0.62, q_valid: false, physics_flags: "non_positive_alpha", reject_reason: "" }
    ],
    drop_charge_results: [
      { drop_id: "drop_001", track_id: "candidate_001", radius_um: 0.73, charge_1e_minus_19_C: 3.21, sigma_charge_total_1e_minus_19_C: 0.12 },
      { drop_id: "drop_002", track_id: "candidate_006", radius_um: 0.79, charge_1e_minus_19_C: 9.62, sigma_charge_total_1e_minus_19_C: 0.15 }
    ],
    platform_velocity_results: [
      { drop_id: "drop_001", platform_id: "P001", voltage_V: 0, velocity_m_s: 0.000122, r2_diagnostic: 0.97 },
      { drop_id: "drop_001", platform_id: "P002", voltage_V: 239, velocity_m_s: -0.000044, r2_diagnostic: 0.95 }
    ]
  },
  analysis_report_md: "# Millikan Analysis Report\n\n运行状态：PARTIAL\n\n有界候选基本电荷：1.604 × 10⁻¹⁹ C\n\n最终元电荷识别：false"
};

export const demoAnalysisResponse: AnalysisResponse = {
  run_dir: "runs/demo_millikan",
  manifest: demoArtifacts.manifest,
  validation_errors: [],
  artifacts: demoArtifacts
};
