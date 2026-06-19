import { demoAnalysisResponse, demoArtifacts, demoMetadata } from "../data/demo";
import type { DesktopApi, NormalRecord, NormalSession, NormalProgressEvent, ProgressEvent } from "../types";

declare global {
  interface Window {
    millikan?: DesktopApi;
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function createDemoApi(): DesktopApi {
  let progressListeners: Array<(progress: ProgressEvent) => void> = [];
  let normalProgressListeners: Array<(progress: NormalProgressEvent) => void> = [];
  let normalRecords: NormalRecord[] = [];
  const emit = (progress: ProgressEvent) => progressListeners.forEach((listener) => listener(progress));
  const emitNormal = (progress: NormalProgressEvent) => normalProgressListeners.forEach((listener) => listener(progress));
  const demoNormalSession = (): NormalSession => ({
    session_root: "runs/normal_demo/session",
    records: normalRecords,
    counts: {
      total: normalRecords.length,
      valid: normalRecords.filter((record) => record.valid).length,
      kept_valid: normalRecords.filter((record) => record.valid && record.kept).length
    },
    inversion: null
  });
  return {
    openVideoDialog: async () => "raw_data/2.mp4",
    openRunDialog: async () => "runs/demo_millikan",
    getDroppedFilePath: async (file: File) => file.name || "",
    inspectVideo: async () => ({ metadata: demoMetadata }),
    detectPlatformBoundaries: async () => ({
      diagnostics: { detected_platform_count: 3, expected_platform_count: 3, flags: [] },
      suggestions: [
        { platform_id: "P001", start_frame: 0, end_frame: 156, confidence: 0.95, reject_reason: "" },
        { platform_id: "P002", start_frame: 166, end_frame: 344, confidence: 0.91, reject_reason: "" },
        { platform_id: "P003", start_frame: 355, end_frame: 542, confidence: 0.89, reject_reason: "" }
      ],
      samples: []
    }),
    runAnalysis: async () => {
      const stages = [
        "inspect video",
        "calibrate grid",
        "tracking droplets",
        "fit stable velocity segments",
        "compute charge results",
        "write visualization outputs",
        "write manifest"
      ];
      for (const [index, label] of stages.entries()) {
        emit({ percent: (index + 1) / stages.length, label });
        await wait(120);
      }
      return demoAnalysisResponse;
    },
    runAutoAnalysis: async () => demoAnalysisResponse,
    loadRun: async () => ({ artifacts: demoArtifacts }),
    validateRun: async () => ({ valid: true, errors: [] }),
    runDownstream: async () => ({ artifacts: demoArtifacts }),
    exportReport: async () => ({ canceled: false, destination: "demo-export" }),
    normalInitialize: async () => ({
      session_root: "runs/normal_demo/session",
      run_root: "runs/normal_demo/records",
      session: demoNormalSession(),
      config: {
        physics: {
          plate_distance_m: 0.005,
          air_viscosity_Pa_s: 1.81e-5,
          pressure_Pa: 101325,
          oil_density_kg_m3: 981,
          cunningham_b_Pa_m: 0.0000082,
          relative_uncertainty_floor: 0.05
        },
        grid: { measurement_distance_m: 0.0015 }
      }
    }),
    normalInspectVideo: async () => ({
      video_path: "raw_data/2.mp4",
      video_url: "",
      metadata: demoMetadata
    }),
    normalPrepareVideo: async () => {
      emitNormal({
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
      session_root: "runs/normal_demo/session",
      video_path: "raw_data/2.mp4",
      video_url: "",
      metadata: demoMetadata,
      boundary: {
        zero_v_start_s: 0.8,
        zero_v_end_s: 5.4,
        source: "auto_suggestion",
        confidence: 0.82,
        diagnostics: { method: "demo" }
      },
      grid: {
        valid: true,
        line_y_px: [120, 220, 320, 420, 520],
        grid_lines_y: [120, 220, 320, 420, 520],
        effective_top_px: 220,
        effective_bottom_px: 420,
        measurement_distance_m: 0.001,
        scale_y_m_per_px: 5e-6,
        flags: []
      },
      session: demoNormalSession(),
      config: {
        physics: {
          plate_distance_m: 0.005,
          air_viscosity_Pa_s: 1.81e-5,
          pressure_Pa: 101325,
          oil_density_kg_m3: 981,
          cunningham_b_Pa_m: 0.0000082,
          relative_uncertainty_floor: 0.05
        },
        grid: { measurement_distance_m: 0.0015 }
      }
    };
    },
    normalConfirmBoundary: async () => ({ session_root: "runs/normal_demo/session", active_video: { state: "boundary_confirmed" }, session: demoNormalSession() }),
    normalSelectTarget: async () => ({ session_root: "runs/normal_demo/session", active_video: { state: "target_selected" }, session: demoNormalSession() }),
    normalSaveMeasurement: async () => {
      emitNormal({
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
      const index = normalRecords.length + 1;
      const record: NormalRecord = {
        record_id: `N${String(index).padStart(3, "0")}`,
        video_path: "raw_data/2.mp4",
        kept: false,
        valid: false,
        q_valid: true,
        status: "pending_crossing_review",
        q_C: 1.602e-19 * index,
        sigma_q_C: 0.09e-19,
        radius_m: 7.8e-7,
        fall_velocity_m_s: 2.4e-4,
        balance_voltage_V: 239,
        flags: [],
        artifacts: {},
        crossings: [
          { event_id: `N${String(index).padStart(3, "0")}-C001`, time_s: 1.8, start_time_s: 1.7, review_start_time_s: 0.8, review_end_time_s: 2.8, grid_line_y_px: 220 }
        ]
      };
      normalRecords = [...normalRecords, record];
      return { session_root: "runs/normal_demo/session", record, session: demoNormalSession() };
    },
    normalPrepareCrossingReview: async (payload) => {
      const record = normalRecords.find((item) => item.record_id === payload.record_id) ?? normalRecords[normalRecords.length - 1];
      const event = record?.crossings?.find((item) => item.event_id === payload.event_id) ?? record?.crossings?.[0];
      const nextEvent = event ? { ...event, review_clip_url: "" } : undefined;
      return { session_root: "runs/normal_demo/session", record, event: nextEvent, session: demoNormalSession() };
    },
    normalReviewCrossing: async (payload) => {
      normalRecords = normalRecords.map((record) => {
        if (record.record_id !== payload.record_id) return record;
        const crossings = (record.crossings ?? []).map((event) => (event.event_id === payload.event_id ? { ...event, review_result: payload.result } : event));
        return { ...record, crossings, status: payload.result === "different_drop" ? "rejected_crossing_identity" : "pending_user_confirmation" };
      });
      const record = normalRecords.find((item) => item.record_id === payload.record_id) ?? normalRecords[0];
      return { session_root: "runs/normal_demo/session", record, session: demoNormalSession() };
    },
    normalSelectRecord: async (payload) => {
      normalRecords = normalRecords.map((record) => (record.record_id === payload.record_id ? { ...record, kept: payload.kept, valid: payload.kept, status: payload.kept ? "accepted" : "rejected_by_user" } : record));
      return demoNormalSession();
    },
    normalRunInversion: async () => ({
      session_root: "runs/normal_demo/session",
      inversion: {
        status: "ok",
        e_hat_C: 1.602e-19,
        sigma_e_C: 0.04e-19,
        valid_q_count: normalRecords.filter((record) => record.valid && record.kept).length,
        comparison: { status: "not_computed" }
      },
      session: {
        ...demoNormalSession(),
        inversion: {
          status: "ok",
          e_hat_C: 1.602e-19,
          sigma_e_C: 0.04e-19,
          valid_q_count: normalRecords.filter((record) => record.valid && record.kept).length,
          comparison: { status: "not_computed" }
        }
      }
    }),
    normalExportSession: async () => ({ canceled: false, destination: "demo-normal-export" }),
    setModeFullscreen: async () => false,
    openPath: async () => undefined,
    onAnalysisProgress: (callback) => {
      progressListeners = [...progressListeners, callback];
      return () => {
        progressListeners = progressListeners.filter((listener) => listener !== callback);
      };
    },
    onNormalProgress: (callback) => {
      normalProgressListeners = [...normalProgressListeners, callback];
      return () => {
        normalProgressListeners = normalProgressListeners.filter((listener) => listener !== callback);
      };
    }
  };
}

export const desktopApi: DesktopApi = window.millikan ?? createDemoApi();
