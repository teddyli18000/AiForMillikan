import { demoAnalysisResponse, demoArtifacts, demoMetadata } from "../data/demo";
import type { DesktopApi, ProgressEvent } from "../types";

declare global {
  interface Window {
    millikan?: DesktopApi;
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function createDemoApi(): DesktopApi {
  let progressListeners: Array<(progress: ProgressEvent) => void> = [];
  const emit = (progress: ProgressEvent) => progressListeners.forEach((listener) => listener(progress));
  return {
    initializeApp: async () => ({
      ok: true,
      checks: [
        { id: "renderer_ready", label: "renderer ready", ok: true },
        { id: "preload_api_ready", label: "preload API ready", ok: true },
        { id: "packaged_worker_health", label: "packaged worker health", ok: true },
        { id: "config_readable", label: "配置资源可读", ok: true },
        { id: "normal_session_readable", label: "普通模式 session 可读", ok: true }
      ],
    }),
    runtimePaths: async () => ({}),
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
    normalInitialize: async () => ({
      session: { records: [], counts: { total: 0, valid: 0, selected_valid: 0 }, eligible_for_inversion: false }
    }),
    normalPrepareVideo: async () => ({
      metadata: demoMetadata,
      video_url: "raw_data/2.mp4",
      boundary: {
        samples: [],
        operations: [{ start_frame: 30, end_frame: 40 }],
        suggestion: {
          selection_frame: 12,
          selection_time_s: 0.4,
          fall_start_frame: 52,
          fall_start_time_s: 1.73,
          fall_end_frame: 180,
          fall_end_time_s: 6,
          end_source: "test_mock"
        }
      },
      grid: { valid: true, grid_lines_y: [40, 80, 120, 160], second_line_y: 80, penultimate_line_y: 120, scale_y_m_per_px: 0.0015 / 40 },
      session: { records: [], counts: { total: 0, valid: 0, selected_valid: 0 }, eligible_for_inversion: false }
    }),
    normalSaveMeasurement: async () => ({
      record: { record_id: "test_record", status: "diagnostic", selected: false, recovery_suggestions: ["重新框选更清晰的油滴。"] },
      session: { records: [{ record_id: "test_record", status: "diagnostic", selected: false }], counts: { total: 1, valid: 0, selected_valid: 0 }, eligible_for_inversion: false }
    }),
    normalSelectRecord: async () => ({ session: { records: [], counts: { total: 0, valid: 0, selected_valid: 0 }, eligible_for_inversion: false } }),
    normalRunInversion: async () => ({ inversion: {}, session: { records: [], counts: { total: 0, valid: 0, selected_valid: 0 }, eligible_for_inversion: false } }),
    normalCreateQaFixture: async () => ({ session: { records: [], counts: { total: 3, valid: 3, selected_valid: 3 }, eligible_for_inversion: true, qa_fixture: true } }),
    normalExportSession: async () => ({ canceled: false }),
    exportReport: async () => ({ canceled: false, destination: "demo-export" }),
    openPath: async () => undefined,
    onAnalysisProgress: (callback) => {
      progressListeners = [...progressListeners, callback];
      return () => {
        progressListeners = progressListeners.filter((listener) => listener !== callback);
      };
    }
  };
}

if (!window.millikan && import.meta.env.MODE !== "test") {
  throw new Error("Millikan preload API is unavailable. Production builds do not use demo data fallback.");
}

export const desktopApi: DesktopApi = window.millikan ?? createDemoApi();
