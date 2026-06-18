import { demoAnalysisResponse, demoArtifacts, demoMetadata } from "../data/demo";
import type { DesktopApi, NormalRecord, NormalSession, ProgressEvent } from "../types";

declare global {
  interface Window {
    millikan?: DesktopApi;
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function createDemoApi(): DesktopApi {
  let progressListeners: Array<(progress: ProgressEvent) => void> = [];
  let normalRecords: NormalRecord[] = [];
  const emit = (progress: ProgressEvent) => progressListeners.forEach((listener) => listener(progress));
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
    normalInitialize: async () => demoNormalSession(),
    normalPrepareVideo: async () => ({
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
        line_y_px: [120, 220, 320, 420, 520],
        effective_top_px: 220,
        effective_bottom_px: 420,
        measurement_distance_m: 0.001,
        scale_y_m_per_px: 5e-6,
        flags: []
      },
      session: demoNormalSession()
    }),
    normalSaveMeasurement: async () => {
      const index = normalRecords.length + 1;
      const record: NormalRecord = {
        record_id: `N${String(index).padStart(3, "0")}`,
        video_path: "raw_data/2.mp4",
        kept: true,
        valid: true,
        q_C: 1.602e-19 * index,
        sigma_q_C: 0.09e-19,
        radius_m: 7.8e-7,
        fall_velocity_m_s: 2.4e-4,
        balance_voltage_V: 239,
        flags: [],
        artifacts: {},
        crossings: [
          { event_id: `N${String(index).padStart(3, "0")}-C001`, time_s: 1.8, review_start_time_s: 0.8, review_end_time_s: 2.8, grid_line_y_px: 220 }
        ]
      };
      normalRecords = [...normalRecords, record];
      return { session_root: "runs/normal_demo/session", record, session: demoNormalSession() };
    },
    normalSelectRecord: async (payload) => {
      normalRecords = normalRecords.map((record) => (record.record_id === payload.record_id ? { ...record, kept: payload.kept } : record));
      return demoNormalSession();
    },
    normalRunInversion: async () => ({
      session_root: "runs/normal_demo/session",
      inversion: {
        status: "ok",
        e_hat_C: 1.602e-19,
        sigma_e_C: 0.04e-19,
        valid_q_count: normalRecords.filter((record) => record.valid && record.kept).length,
        comparison: { quantized_favored: true }
      },
      session: {
        ...demoNormalSession(),
        inversion: {
          status: "ok",
          e_hat_C: 1.602e-19,
          sigma_e_C: 0.04e-19,
          valid_q_count: normalRecords.filter((record) => record.valid && record.kept).length,
          comparison: { quantized_favored: true }
        }
      }
    }),
    normalExportSession: async () => ({ canceled: false, destination: "demo-normal-export" }),
    openPath: async () => undefined,
    onAnalysisProgress: (callback) => {
      progressListeners = [...progressListeners, callback];
      return () => {
        progressListeners = progressListeners.filter((listener) => listener !== callback);
      };
    }
  };
}

export const desktopApi: DesktopApi = window.millikan ?? createDemoApi();
