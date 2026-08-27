import type {
  NormalBoundary,
  NormalCrossingEvent,
  NormalInversionResult,
  NormalRecord,
  NormalSession,
  RunArtifacts,
  VideoMetadata
} from "../types";

type NormalPreset = {
  boundary: [number, number];
  voltage: number;
  q: number;
  sigmaQ: number;
  radiusUm: number;
  velocity: number;
  sigmaV: number;
  r2: number;
  points: number;
  scale: number;
  etaEff: number;
  sensitivity: number;
  crossings: number;
};

export const normalPresets: NormalPreset[] = [
  {
    boundary: [2.1, 3.6],
    voltage: 296,
    q: 8.1689e-19,
    sigmaQ: 0.2369e-19,
    radiusUm: 1.0845,
    velocity: 1.4745e-4,
    sigmaV: 2.593e-6,
    r2: 0.989,
    points: 37,
    scale: 2.174e-6,
    etaEff: 1.703e-5,
    sensitivity: 1.554,
    crossings: 0
  },
  {
    boundary: [8.9, 11.2],
    voltage: 148,
    q: 12.856e-19,
    sigmaQ: 0.2669e-19,
    radiusUm: 2.1264,
    velocity: 3.4746e-4,
    sigmaV: 0.215e-6,
    r2: 0.974,
    points: 45,
    scale: 6.098e-6,
    etaEff: 1.763e-5,
    sensitivity: 1.528,
    crossings: 2
  },
  {
    boundary: [3.4, 4.9],
    voltage: 212,
    q: 17.536e-19,
    sigmaQ: 0.8657e-19,
    radiusUm: 2.0235,
    velocity: 2.9667e-4,
    sigmaV: 0.707e-6,
    r2: 0.996,
    points: 17,
    scale: 4.808e-6,
    etaEff: 1.759e-5,
    sensitivity: 1.529,
    crossings: 2
  }
];

const frameSvg = (label: string, x: number, y: number) =>
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#071019"/><g stroke="#334155" stroke-width="2" opacity=".75">${[150, 250, 350, 450, 550].map((line) => `<path d="M120 ${line}H1160"/>`).join("")}</g><path d="M${x - 12} 120 C${x + 8} 250 ${x - 18} 390 ${x} ${y}" stroke="#38bdf8" stroke-width="5" fill="none"/><circle cx="${x}" cy="${y}" r="17" fill="none" stroke="#4ade80" stroke-width="7"/><text x="${x + 28}" y="${y + 8}" font-family="Arial" font-size="28" fill="#4ade80">${label}</text><text x="34" y="680" font-family="Arial" font-size="25" fill="#e2e8f0">tracked trajectory · +Y downward</text></svg>`
  );

export function normalPresetIndex(session: NormalSession | null): number {
  return Math.min(normalPresets.length - 1, session?.records?.length ?? 0);
}

export function normalPresetBoundary(index: number): NormalBoundary {
  const preset = normalPresets[Math.min(index, normalPresets.length - 1)];
  return {
    zero_v_start_s: preset.boundary[0],
    zero_v_end_s: preset.boundary[1],
    source: "auto_suggestion"
  };
}

export function createNormalRecord(index: number, source?: NormalRecord | null): NormalRecord {
  const preset = normalPresets[Math.min(index, normalPresets.length - 1)];
  const recordId = source?.record_id || `N${String(index + 1).padStart(3, "0")}`;
  const crossings = createCrossings(index, preset, (source?.crossings ?? source?.crossing_events) as NormalCrossingEvent[] | undefined);
  const traceFit = {
    slope_px_s: preset.velocity / preset.scale,
    slope_sigma_px_s: preset.sigmaV / preset.scale,
    scale_y_m_per_px: preset.scale,
    velocity_m_s: preset.velocity,
    sigma_v_m_s: preset.sigmaV,
    fit_point_count: preset.points,
    duration_s: preset.boundary[1] - preset.boundary[0],
    r2: preset.r2
  };
  return {
    ...source,
    record_id: recordId,
    kept: source?.kept ?? false,
    valid: source?.valid ?? false,
    q_valid: true,
    status: crossings.length ? "pending_crossing_review" : "pending_user_confirmation",
    q_C: preset.q,
    sigma_q_C: preset.sigmaQ,
    radius_m: preset.radiusUm * 1e-6,
    fall_velocity_m_s: preset.velocity,
    balance_voltage_V: preset.voltage,
    time_window: {
      zero_v_start_s: preset.boundary[0],
      zero_v_end_s: preset.boundary[1],
      source: "manual_ui"
    },
    fit: traceFit,
    q: {
      valid: true,
      q_C: preset.q,
      sigma_q_C: preset.sigmaQ,
      radius_m: preset.radiusUm * 1e-6,
      eta_eff_Pa_s: preset.etaEff,
      velocity_m_s: preset.velocity,
      balance_voltage_V: preset.voltage,
      uncertainty_budget: {
        included: [{ component: "linear_regression_slope" }, { component: "q_velocity_propagation" }],
        not_included: ["shared_systematic_parameters"]
      },
      calculation_trace: {
        model: "balance_voltage_zero_v_fall",
        fit: traceFit,
        physics: {
          balance_voltage_V: preset.voltage,
          cunningham_length_m: 8.118e-8,
          radius_m: preset.radiusUm * 1e-6,
          eta_eff_Pa_s: preset.etaEff,
          q_velocity_sensitivity: preset.sensitivity,
          plate_distance_m: 0.005
        },
        result: { q_C: preset.q, sigma_q_C: preset.sigmaQ }
      }
    },
    flags: [],
    crossings,
    track_review_frames:
      source?.track_review_frames?.length
        ? source.track_review_frames
        : Array.from({ length: 14 }, (_, frameIndex) => ({
            frame_index: Math.round(preset.boundary[0] * 30) + frameIndex * 2,
            time_s: preset.boundary[0] + frameIndex / 15,
            image_url: frameSvg(`drop ${index + 1}`, 390 + index * 225, 260 + frameIndex * 18),
            width: 1280,
            height: 720
          }))
  };
}

function createCrossings(index: number, preset: NormalPreset, source?: NormalCrossingEvent[]): NormalCrossingEvent[] {
  if (!preset.crossings) return [];
  const backendEvents = Array.isArray(source) ? source.slice(0, preset.crossings) : [];
  if (backendEvents.length) {
    return backendEvents.map((event, crossingIndex) => ({
      ...event,
      event_id: event.event_id || `N${String(index + 1).padStart(3, "0")}-C${String(crossingIndex + 1).padStart(3, "0")}`,
      review_result: event.review_result
    }));
  }
  return Array.from({ length: preset.crossings }, (_, crossingIndex) => {
    const time = preset.boundary[0] + 0.65 + crossingIndex * 0.72;
    return {
      event_id: `N${String(index + 1).padStart(3, "0")}-C${String(crossingIndex + 1).padStart(3, "0")}`,
      time_s: time,
      start_time_s: time,
      review_start_time_s: Math.max(0, time - 1),
      review_end_time_s: time + 1,
      grid_line_y_px: 250 + crossingIndex * 100
    };
  });
}

export function replaceSessionRecord(session: NormalSession | null, record: NormalRecord): NormalSession {
  const records = [...(session?.records ?? [])];
  const existing = records.findIndex((row) => row.record_id === record.record_id);
  if (existing >= 0) records[existing] = record;
  else records.push(record);
  return withNormalCounts({ ...(session ?? { session_root: "runs/normal_presentation" }), records });
}

export function withNormalCounts(session: NormalSession): NormalSession {
  const records = session.records ?? [];
  const accepted = records.filter((record) => record.kept && record.status === "accepted");
  return {
    ...session,
    records,
    counts: {
      ...(session.counts ?? {}),
      total: records.length,
      q_ready: records.filter((record) => record.q_valid).length,
      valid: accepted.length,
      kept_valid: accepted.length,
      selected_valid: accepted.length
    }
  };
}

export function normalInversion(records: NormalRecord[]): NormalInversionResult {
  const accepted = records.slice(0, 3);
  const eHat = 1.6135499335965642e-19;
  const sigmaE = 0.02577402699853812e-19;
  const assignmentsN = [5, 8, 11];
  const assignments = accepted.map((record, index) => {
    const q = normalPresets[index].q;
    const sigma = normalPresets[index].sigmaQ;
    const n = assignmentsN[index];
    const nearest = n * eHat;
    return {
      record_id: record.record_id,
      q_C: q,
      sigma_q_C: sigma,
      sigma_eff_C: sigma,
      n,
      nearest_quantized_charge_C: nearest,
      residual_C: q - nearest,
      residual_sigma: (q - nearest) / sigma
    };
  });
  const candidateRows = [
    [1.6135499335965642, 0.3062770893, 0.2814169663, [5, 8, 11]],
    [1.4098550582, 0.8949917285, 2.4030305821, [6, 9, 12]],
    [2.1147825873, 0.8949917285, 2.4030305821, [4, 6, 8]],
    [1.3980630747, 0.904140063, 2.4524077603, [6, 9, 13]],
    [1.6283161505, 0.9157699332, 2.5159037118, [5, 8, 10]],
    [2.087435828, 1.1849482596, 4.212307134, [4, 6, 9]]
  ] as const;
  const charts = {
    charge_distribution: assignments.map((row) => ({ q_C: row.q_C, sigma_q_C: row.sigma_q_C, n: row.n, nearest_C: row.nearest_quantized_charge_C })),
    residuals: assignments.map((row) => ({ q_C: row.q_C, residual_sigma: row.residual_sigma, n: row.n, record_id: row.record_id })),
    quantized_levels: Array.from({ length: 12 }, (_, index) => ({ n: index + 1, charge_C: (index + 1) * eHat }))
  };
  return {
    reliable: false,
    status: "exploratory",
    e_hat_C: eHat,
    sigma_e_C: sigmaE,
    weighted_rms: 0.3062770893,
    chi2: 0.2814169663,
    num_used: 3,
    valid_q_count: 3,
    search_interval_C: [1.35e-19, 2.5e-19],
    sigma_floor_C: 0,
    converged: true,
    boundary_hit: false,
    reference_comparison: {
      reference_e_C: 1.602176634e-19,
      reference_name: "SI defining constant",
      relative_uncertainty_percent: 1.5973492026,
      percent_error_vs_reference: 0.7098655264,
      used_for_inversion: false
    },
    assignments,
    candidates: candidateRows.map(([e, rms, chi2, integers]) => ({
      e_C: e * 1e-19,
      weighted_rms: rms,
      chi2,
      converged: true,
      boundary_hit: false,
      integer_assignment: [...integers]
    })),
    charts,
    plots_data: charts,
    quantized_alignment: { model: "integer_multiple_weighted_residual", weighted_rms: 0.3062770893 },
    comparison: { status: "not_computed", reason: "No fitted continuous baseline is defined in Normal v1." },
    flags: ["exploratory_small_sample"]
  };
}

const experimentalE = 1.9226e-19;
const experimentalCharges = [3.861, 5.742, 7.721, 9.581, 11.59, 13.39, 15.49, 17.21, 19.36, 21.03, 23.18];
const experimentalResiduals = [0.083, -0.135, 0.159, -0.167, 0.057, -0.194, 0.109, -0.219, 0.069, -0.166, 0.113];

const tracks = Array.from({ length: 13 }, (_, index) => {
  const column = index % 5;
  const row = Math.floor(index / 5);
  const x = 255 + column * 165 + row * 28;
  const startY = 125 + row * 55 + (index % 2) * 18;
  const direction = index % 4 === 0 ? -1 : 1;
  return {
    track_id: `candidate_${String(index + 1).padStart(3, "0")}`,
    drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
    quality_score: index < 11 ? 0.94 - index * 0.025 : 0.48 - (index - 11) * 0.07,
    keep: index < 11,
    q_valid: index < 11,
    reject_reasons: index < 11 ? "" : index === 11 ? "insufficient_platform_coverage" : "stationary_grid_candidate",
    points: Array.from({ length: 6 }, (_, pointIndex) => ({
      frame_idx: pointIndex * 88,
      x_px: x + Math.sin(pointIndex * 0.9 + index) * 10,
      y_px: startY + direction * pointIndex * (67 + (index % 3) * 8),
      valid: true
    }))
  };
});

export const experimentalArtifacts: RunArtifacts = {
  run_dir: "runs/experimental_presentation",
  manifest: {
    schema_version: 1,
    run_dir: "runs/experimental_presentation",
    status: {
      video_readable: true,
      valid_for_q: true,
      valid_for_elementary_charge: true,
      elementary_estimation_ready: true,
      bounded_estimate_available: true,
      quantization_supported: true,
      elementary_status: "fundamental_spacing_identified",
      flags: []
    },
    counts: { platforms: 3, drops: 13, valid_drops: 11, quality_kept_drops: 11, track_rows: 858, segments: 33 },
    files: { diagnostic_overlay_jpg: "diagnostic_overlay.jpg", plots_data_json: "plots_data.json" }
  },
  validity_report: {
    overall_valid_for_q: true,
    overall_valid_for_elementary_charge: true,
    elementary_estimation_ready: true,
    bounded_estimate_available: true,
    quantization_supported: true,
    elementary_status: "fundamental_spacing_identified",
    blocking_failed_checks: [],
    combined_flags: ["all_required_checks_passed"],
    checks: [
      { id: "video_readable", passed: true, message: "视频可读取，帧序列完整。" },
      { id: "scale_calibrated", passed: true, message: "网格标定与物理尺度检查通过。" },
      { id: "platform_count", passed: true, message: "3 个电压平台边界与设定一致。" },
      { id: "tracking_coverage", passed: true, message: "追踪到 13 颗候选油滴，其中 11 颗满足完整性要求。" },
      { id: "drop_q_valid", passed: true, message: "11 颗油滴的 q 计算与随机不确定度有效。" },
      { id: "primitive_assignment", passed: true, message: "整数分配为 primitive assignment。" },
      { id: "elementary_fundamental_spacing_identified", passed: true, message: "元电荷间距识别检查通过。" }
    ]
  },
  elementary_charge_result: {
    valid: true,
    fit_valid: true,
    bounded_estimate_available: true,
    quantization_favored: true,
    quantization_supported: true,
    primitive_assignment_supported: true,
    fundamental_spacing_identified: true,
    status: "fundamental_spacing_identified",
    reason: "All required scientific checks passed.",
    flags: [],
    num_used_drops: 11,
    elementary_charge: {
      e_hat_C: experimentalE,
      sigma_e_C: 0.0318e-19,
      ci_95_C: [1.8603e-19, 1.9849e-19],
      profile_ci_95_C: [1.8651e-19, 1.9812e-19],
      search_interval_C: [1.35e-19, 1.9e-19]
    }
  },
  model_comparison: {
    delta_elpd: 14.72,
    evidence_label: "strong",
    quantized_elpd: -10.84,
    continuous_elpd: -25.56
  },
  uncertainty_details: {
    status: "complete",
    random_uncertainty: "per-drop random q uncertainty propagated",
    systematic_uncertainty: "shared physical-parameter draw propagated"
  },
  drop_results: {
    fit: { alpha_m_s: 2.86e-4, gamma_m_s_V: 1.17e-6, r2: 0.991 },
    result: { charge_abs_C: 3.861e-19, radius_m: 0.82e-6, q_valid: true }
  },
  visualization_layers: {
    frame: { width: 1280, height: 720, fps: 30, frame_count: 1050, duration_s: 35 },
    coordinate_system: { origin: "top_left_video_pixel", x_positive: "right", y_positive: "down" },
    layers: [
      { id: "microscope_roi", type: "rect", x: 120, y: 72, w: 1010, h: 575, label: "Microscope ROI" },
      { id: "tracking_roi", type: "rect", x: 165, y: 88, w: 915, h: 535, label: "Tracking ROI" },
      { id: "horizontal_grid_lines", type: "line_set", orientation: "horizontal", positions_px: [120, 206, 292, 378, 464, 550] },
      { id: "vertical_grid_lines", type: "line_set", orientation: "vertical", positions_px: [230, 360, 490, 620, 750, 880, 1010] },
      { id: "drop_tracks", type: "multi_frame_point_series", tracks }
    ]
  },
  plots_data: {
    schema_version: 2,
    status: "supported",
    summary: { quantization_favored: true, quantization_supported: true, fundamental_spacing_identified: true },
    charts: {
      charge_distribution: {
        observations: experimentalCharges.map((value, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          q_C: value * 1e-19,
          sigma_q_C: (0.12 + (index % 4) * 0.025) * 1e-19,
          n_hat: index + 2,
          assignment_probability_given_e: 0.91 + (index % 4) * 0.018
        })),
        quantized_density: Array.from({ length: 80 }, (_, index) => {
          const q = (2.8 + index * 0.27) * 1e-19;
          const phase = q / experimentalE;
          const distance = Math.abs(phase - Math.round(phase));
          return { q_C: q, density: 0.12 + 0.92 * Math.exp(-42 * distance * distance) };
        }),
        continuous_density: Array.from({ length: 80 }, (_, index) => ({
          q_C: (2.8 + index * 0.27) * 1e-19,
          density: 0.28 + 0.09 * Math.sin(index * 0.18) ** 2
        })),
        quantized_levels: Array.from({ length: 13 }, (_, index) => ({ n: index + 1, charge_C: (index + 1) * experimentalE }))
      },
      integer_assignment: {
        points: experimentalCharges.map((value, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          q_C: value * 1e-19,
          n_hat: index + 2,
          nearest_quantized_charge_C: (index + 2) * experimentalE,
          residual_C: experimentalResiduals[index] * 0.16e-19,
          normalized_residual: experimentalResiduals[index],
          assignment_probability_given_e: 0.91 + (index % 4) * 0.018
        }))
      },
      phase_residual: {
        points: experimentalResiduals.map((phase, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          phase_residual: phase,
          n_hat: index + 2
        }))
      },
      model_comparison: {
        delta_elpd: 14.72,
        quantized_elpd: -10.84,
        continuous_elpd: -25.56,
        status: "quantization_supported",
        per_drop: [1.42, 0.93, 1.56, 1.18, 1.74, 0.88, 1.36, 1.08, 1.55, 1.27, 1.75].map((value, index) => ({
          drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
          delta_log_predictive_density: value
        }))
      }
    }
  },
  tables: {
    platforms: [
      { platform_id: "P001", start_frame: 0, end_frame: 324, voltage_V: 0, source: "auto_boundary_manual_voltage" },
      { platform_id: "P002", start_frame: 336, end_frame: 681, voltage_V: 239, source: "auto_boundary_manual_voltage" },
      { platform_id: "P003", start_frame: 694, end_frame: 1049, voltage_V: 362, source: "auto_boundary_manual_voltage" }
    ],
    candidate_tracks_summary: tracks.map((track, index) => ({
      rank: index + 1,
      candidate_id: track.track_id,
      score_total: track.quality_score,
      q_valid: track.q_valid,
      charge_abs_C: index < 11 ? experimentalCharges[index] * 1e-19 : null,
      reject_reason: track.reject_reasons
    })),
    drop_charge_results: experimentalCharges.map((value, index) => ({
      drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
      track_id: `candidate_${String(index + 1).padStart(3, "0")}`,
      radius_um: 0.82 + index * 0.067,
      charge_1e_minus_19_C: value,
      sigma_charge_total_1e_minus_19_C: 0.12 + (index % 4) * 0.025
    })),
    platform_velocity_results: Array.from({ length: 11 }, (_, dropIndex) =>
      [0, 239, 362].map((voltage, platformIndex) => ({
        drop_id: `drop_${String(dropIndex + 1).padStart(3, "0")}`,
        platform_id: `P${String(platformIndex + 1).padStart(3, "0")}`,
        voltage_V: voltage,
        velocity_m_s: (2.86 - platformIndex * 1.21 + dropIndex * 0.045) * 1e-4,
        r2_diagnostic: 0.991 - ((dropIndex + platformIndex) % 5) * 0.006
      }))
    ).flat()
  },
  analysis_report_md: "# Millikan Analysis Report\n\n运行状态：PASS\n\n追踪候选：13\n\n有效油滴：11\n\n元电荷估计：1.9226 × 10⁻¹⁹ C"
};

export const experimentalProgressSchedule = [
  { atMs: 0, percent: 0.02, label: "inspect video" },
  { atMs: 3200, percent: 0.13, label: "calibrate grid" },
  { atMs: 8400, percent: 0.29, label: "tracking droplets" },
  { atMs: 20700, percent: 0.63, label: "fit stable velocity segments" },
  { atMs: 27100, percent: 0.79, label: "compute charge results" },
  { atMs: 31800, percent: 0.92, label: "write visualization outputs" },
  { atMs: 34200, percent: 0.98, label: "write manifest" }
];

export function fallbackMetadata(path: string): VideoMetadata {
  return { path, readable: true, width: 1280, height: 720, fps: 30, frame_count: 1050, duration_s: 35 };
}
