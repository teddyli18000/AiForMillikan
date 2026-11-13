import "@testing-library/jest-dom/vitest";
import type { DesktopApi, NormalProgressEvent, NormalRecord, NormalSession } from "./src/types";

const frameImage =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#101820"/><circle cx="160" cy="90" r="12" fill="none" stroke="#22c55e" stroke-width="4"/></svg>'
  );

const metadata = {
  path: "media/videos/2u.mp4",
  readable: true,
  width: 1280,
  height: 720,
  fps: 30,
  frame_count: 900,
  duration_s: 30
};

const grid = {
  valid: true,
  line_y_px: [120, 220, 320, 420, 520],
  grid_lines_y: [120, 220, 320, 420, 520],
  effective_top_px: 220,
  effective_bottom_px: 420,
  measurement_distance_m: 0.001,
  scale_y_m_per_px: 5e-6,
  flags: []
};

const backendConfig = {
  physics: {
    plate_distance_m: 0.005,
    air_viscosity_Pa_s: 1.83e-5,
    pressure_kPa: 101.325,
    oil_density_kg_m3: 981,
    cunningham_b_kPa_m: 0.000008226,
    gravity_m_s2: 9.79
  },
  grid: { measurement_distance_m: 0.0015 }
};

const sessionRoot = "runs/normal_demo/session";

function createTestDesktopApi(): DesktopApi {
  let listeners: Array<(progress: NormalProgressEvent) => void> = [];
  let records: NormalRecord[] = [];
  let balanceVoltage = 239;
  let target: Record<string, unknown> = {};
  let parameterOverrides: Record<string, unknown> = {};

  const emit = (progress: NormalProgressEvent) => listeners.forEach((listener) => listener(progress));

  const sessionOf = (activeVideo: Record<string, unknown> | null = null): NormalSession => ({
    session_root: sessionRoot,
    records,
    active_video: activeVideo,
    counts: {
      total: records.length,
      kept_valid: records.filter((record) => record.valid && record.kept).length
    },
    inversion: null
  });

  const adjustmentVideo = (record: NormalRecord): Record<string, unknown> => ({
    state: "boundary_confirmed",
    path: record.video_path,
    video_url: "demo-normal-video.mp4",
    metadata: record.metadata,
    boundary: record.time_window,
    grid: record.grid,
    adjustment_source_record_id: record.record_id,
    adjustment: {
      record_id: record.record_id,
      target: record.target,
      balance_voltage_V: record.balance_voltage_V,
      balance_confirmed: true,
      parameter_overrides: record.parameter_overrides ?? {}
    }
  });

  const inversionOf = () => {
    const accepted = records.filter((record) => record.valid && record.kept);
    const rows = accepted.length >= 3 ? accepted : [1, 2, 3].map((index) => ({
      record_id: `demo-q-${index}`,
      q_C: 1.602e-19 * index,
      sigma_q_C: 0.08e-19,
      valid: true,
      kept: true
    }) as NormalRecord);
    const eHat = 1.602e-19;
    const assignments = rows.map((record, index) => {
      const q = Number(record.q_C ?? eHat * (index + 1));
      const sigma = Number(record.sigma_q_C ?? 0.08e-19);
      const n = Math.max(1, Math.round(q / eHat));
      const nearest = n * eHat;
      return {
        record_id: record.record_id,
        q_C: q,
        sigma_q_C: sigma,
        sigma_eff_C: Math.sqrt(sigma * sigma + (0.02e-19) ** 2),
        n,
        nearest_quantized_charge_C: nearest,
        residual_C: q - nearest,
        residual_sigma: (q - nearest) / sigma
      };
    });
    return {
      status: rows.length === 3 ? "exploratory" : "reliable",
      e_hat_C: eHat,
      sigma_e_C: 0.035e-19,
      reference_comparison: {
        reference_e_C: 1.602176634e-19,
        reference_name: "SI defining constant",
        relative_uncertainty_percent: (0.035e-19 / eHat) * 100,
        percent_error_vs_reference: (Math.abs(eHat - 1.602176634e-19) / 1.602176634e-19) * 100,
        used_for_inversion: false
      },
      weighted_rms: 0.42,
      chi2: 0.53,
      num_used: rows.length,
      valid_q_count: rows.length,
      search_interval_C: [1.35e-19, 1.9e-19],
      sigma_floor_C: 0.02e-19,
      converged: true,
      boundary_hit: false,
      assignments,
      candidates: [
        { e_C: eHat, weighted_rms: 0.42, chi2: 0.53, converged: true, boundary_hit: false, integer_assignment: assignments.map((row) => row.n) },
        { e_C: 1.548e-19, weighted_rms: 1.31, chi2: 5.16, converged: true, boundary_hit: false, integer_assignment: assignments.map((row) => Math.max(1, row.n + (row.n > 2 ? 1 : 0))) },
        { e_C: 1.711e-19, weighted_rms: 1.84, chi2: 10.15, converged: false, boundary_hit: false, integer_assignment: assignments.map((row) => Math.max(1, row.n - 1)) }
      ],
      charts: {
        charge_distribution: assignments.map((row) => ({ q_C: row.q_C, sigma_q_C: row.sigma_q_C, n: row.n, nearest_C: row.nearest_quantized_charge_C })),
        residuals: assignments.map((row) => ({ q_C: row.q_C, residual_sigma: row.residual_sigma, n: row.n, record_id: row.record_id })),
        quantized_levels: Array.from({ length: Math.max(...assignments.map((row) => row.n)) + 1 }, (_, index) => ({
          n: index + 1,
          charge_C: (index + 1) * eHat
        }))
      },
      flags: rows.length === 3 ? ["exploratory_small_sample"] : []
    };
  };

  return {
    openVideoDialog: async () => "media/videos/2u.mp4",
    getDroppedFilePath: async (file: File) => file.name || "",
    normalInitialize: async () => ({
      session_root: sessionRoot,
      run_root: "runs/normal_demo/records",
      session: sessionOf(),
      config: backendConfig
    }),
    normalInspectVideo: async () => ({
      video_path: metadata.path,
      video_url: "demo-normal-video.mp4",
      metadata
    }),
    normalPrepareVideo: async () => {
      emit({
        request_id: "demo",
        operation: "prepare_video",
        stage: "sample_voltage_region",
        label: "正在采样电压显示区域",
        current: 12,
        total: 40,
        unit: "frames",
        fraction: 0.3,
        indeterminate: false
      });
      return {
        session_root: sessionRoot,
        video_path: metadata.path,
        video_url: "demo-normal-video.mp4",
        metadata,
        boundary: {
          zero_v_start_s: 0.8,
          zero_v_end_s: 5.4,
          source: "auto_suggestion",
          confidence: 0.82,
          diagnostics: { method: "demo" }
        },
        grid,
        session: sessionOf(),
        config: backendConfig
      };
    },
    normalConfirmBoundary: async (payload) => {
      const fps = 30;
      const frameCount = 900;
      const startFrame = Math.max(0, Math.min(frameCount - 1, Math.round(Number(payload.boundary.zero_v_start_s || 0) * fps)));
      const endFrame = Math.max(startFrame, Math.min(frameCount - 1, Math.round(Number(payload.boundary.zero_v_end_s || 0) * fps)));
      const boundary = {
        zero_v_start_s: startFrame / fps,
        zero_v_end_s: endFrame / fps,
        zero_v_start_frame: startFrame,
        zero_v_end_frame: endFrame,
        source: payload.boundary.source ?? "manual_ui",
        selection_window: {
          start_s: Math.max(0, startFrame - Math.round(0.5 * fps)) / fps,
          end_s: Math.min(frameCount - 1, startFrame + Math.round(0.5 * fps)) / fps,
          start_frame: Math.max(0, startFrame - Math.round(0.5 * fps)),
          end_frame: Math.min(frameCount - 1, startFrame + Math.round(0.5 * fps)),
          source: "normal_v1_default"
        }
      };
      return {
        session_root: sessionRoot,
        active_video: { state: "boundary_confirmed", boundary },
        session: sessionOf()
      };
    },
    normalSelectTarget: async (payload) => {
      balanceVoltage = Number(payload.balance_voltage_V);
      target = (payload.target as Record<string, unknown>) ?? {};
      parameterOverrides = (payload.parameter_overrides as Record<string, unknown>) ?? {};
      return { session_root: sessionRoot, active_video: { state: "target_selected" }, session: sessionOf() };
    },
    normalSaveMeasurement: async () => {
      emit({
        request_id: "demo",
        operation: "save_measurement",
        stage: "track_frames",
        label: "正在逐帧追踪油滴",
        current: 80,
        total: 120,
        unit: "frames",
        fraction: 0.67,
        indeterminate: false
      });
      const index = records.length + 1;
      const q_C = 1.602e-19 * index;
      const fit = {
        slope_px_s: 48,
        slope_sigma_px_s: 1.8,
        scale_y_m_per_px: 5e-6,
        velocity_m_s: 2.4e-4,
        sigma_v_m_s: 9e-6,
        fit_point_count: 42,
        duration_s: 1.4,
        r2: 0.993
      };
      const record: NormalRecord = {
        record_id: `N${String(index).padStart(3, "0")}`,
        video_path: metadata.path,
        kept: false,
        valid: false,
        q_valid: true,
        status: "pending_crossing_review",
        q_C,
        sigma_q_C: 0.09e-19,
        radius_m: 7.8e-7,
        fall_velocity_m_s: 2.4e-4,
        balance_voltage_V: balanceVoltage,
        target,
        parameter_overrides: parameterOverrides,
        metadata,
        grid,
        time_window: { zero_v_start_s: 0.8, zero_v_end_s: 5.13 },
        fit,
        q: {
          valid: true,
          q_C,
          sigma_q_C: 0.09e-19,
          radius_m: 7.8e-7,
          eta_eff_Pa_s: 1.72e-5,
          velocity_m_s: 2.4e-4,
          balance_voltage_V: balanceVoltage,
          calculation_trace: {
            model: "balance_voltage_zero_v_fall",
            fit,
            physics: {
              balance_voltage_V: balanceVoltage,
              cunningham_length_m: 8.12e-8,
              radius_m: 7.8e-7,
              eta_eff_Pa_s: 1.72e-5,
              q_velocity_sensitivity: 1.56,
              plate_distance_m: 0.005
            },
            result: { q_C, sigma_q_C: 0.09e-19 }
          }
        },
        track_review_frames: Array.from({ length: 10 }, (_, frameIndex) => ({
          frame_index: 40 + frameIndex,
          time_s: 1.4 + frameIndex / 30,
          image_url: frameImage,
          width: 1280,
          height: 720
        })),
        crossings: [
          { event_id: `N${String(index).padStart(3, "0")}-C001`, time_s: 1.8, start_time_s: 1.7, review_start_time_s: 0.8, review_end_time_s: 2.8, grid_line_y_px: 220 }
        ]
      };
      records = [...records, record];
      return { session_root: sessionRoot, record, session: sessionOf() };
    },
    normalPrepareCrossingReview: async (payload) => {
      const record = records.find((item) => item.record_id === payload.record_id) ?? records[records.length - 1];
      const event = record?.crossings?.find((item) => item.event_id === payload.event_id) ?? record?.crossings?.[0];
      const review_frames = Array.from({ length: 8 }, (_, frameIndex) => ({
        frame_index: 52 + frameIndex,
        time_s: 1.72 + frameIndex / 30,
        image_url: frameImage,
        source_video_box: { x: 96, y: 96, width: 96, height: 96 }
      }));
      const nextEvent = event ? { ...event, review_clip_url: "", review_frames } : undefined;
      return { session_root: sessionRoot, record, event: nextEvent, session: sessionOf() };
    },
    normalReviewCrossing: async (payload) => {
      records = records.map((record) => {
        if (record.record_id !== payload.record_id) return record;
        const crossings = (record.crossings ?? []).map((event) => (event.event_id === payload.event_id ? { ...event, review_result: payload.result } : event));
        return { ...record, crossings, status: payload.result === "different_drop" ? "rejected_crossing_identity" : "pending_user_confirmation" };
      });
      const record = records.find((item) => item.record_id === payload.record_id) ?? records[0];
      const activeVideo = payload.result === "different_drop" && record ? adjustmentVideo(record) : null;
      return { session_root: sessionRoot, record, session: sessionOf(activeVideo) };
    },
    normalSelectRecord: async (payload) => {
      records = records.map((record) => (record.record_id === payload.record_id ? { ...record, kept: payload.kept, valid: payload.kept, status: payload.kept ? "accepted" : "rejected_by_user" } : record));
      const record = records.find((item) => item.record_id === payload.record_id);
      return sessionOf(!payload.kept && record ? adjustmentVideo(record) : null);
    },
    normalStartNextDroplet: async (payload) => {
      const sourceRecord = records.find((record) => record.record_id === payload.record_id) ?? records.at(-1);
      const activeVideo = payload.mode === "same_video"
        ? {
            state: "boundary_confirmed",
            path: sourceRecord?.video_path ?? metadata.path,
            video_url: "demo-normal-video.mp4",
            metadata: sourceRecord?.metadata ?? metadata,
            boundary: sourceRecord?.time_window ?? {
              zero_v_start_s: 0.8,
              zero_v_end_s: 5.13,
              zero_v_start_frame: 24,
              zero_v_end_frame: 154,
              selection_window: { start_s: 0.3, end_s: 1.3, start_frame: 9, end_frame: 39, source: "normal_v1_default" }
            },
            grid: sourceRecord?.grid ?? grid,
            previous_balance_voltage_V: sourceRecord?.balance_voltage_V ?? balanceVoltage,
            previous_parameter_overrides: sourceRecord?.parameter_overrides ?? parameterOverrides
          }
        : null;
      return {
        session_root: sessionRoot,
        active_video: activeVideo,
        session: sessionOf(activeVideo)
      };
    },
    normalRunInversion: async () => {
      const inversion = inversionOf();
      return {
        session_root: sessionRoot,
        inversion,
        session: { ...sessionOf(), inversion }
      };
    },
    normalExportSession: async () => ({ canceled: false, destination: "demo-normal-export" }),
    onNormalProgress: (callback) => {
      listeners = [...listeners, callback];
      return () => {
        listeners = listeners.filter((listener) => listener !== callback);
      };
    }
  };
}

(window as Window & { millikan: DesktopApi }).millikan = createTestDesktopApi();
