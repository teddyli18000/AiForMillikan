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
    suggestNormalWindow: async () => ({
      suggested_window: { fall_start_frame: 8, fall_end_frame: 510, fall_start_time_s: 0.27, fall_end_time_s: 17.0, flags: ["demo_window"] },
      operations: []
    }),
    runNormalSingleDrop: async () => ({
      run_dir: "runs/demo_normal",
      manifest: {
        schema_version: 1,
        mode: "normal_balance_fall",
        run_dir: "runs/demo_normal",
        counts: { usable_q_records: 1, tracking_points: 140, detected_tracking_points: 132 },
        status: { valid_for_q: true, flags: ["systematic_uncertainty_incomplete"] }
      },
      normal_result: {
        mode: "normal_balance_fall",
        run_dir: "runs/demo_normal",
        q_record: {
          record_id: `q_demo_${Date.now()}`,
          q_C: 4.82e-19,
          sigma_q_C: 0.16e-19,
          usable_for_inversion: true,
          selected: true,
          flags: ["systematic_uncertainty_incomplete"]
        }
      },
      artifacts: demoArtifacts
    }),
    estimateNormalElementary: async (payload) => ({
      usable_q_count: payload.q_records.filter((record) => record.selected !== false && record.usable_for_inversion).length,
      reportable: payload.q_records.length >= 3,
      normal_algorithm: {
        valid: payload.q_records.length >= 3,
        status: payload.q_records.length >= 3 ? "success" : "insufficient_q_records",
        e_hat_C: 1.602e-19,
        sigma_e_C: 0.04e-19
      },
      experimental_algorithm: {
        status: "bounded_estimate_evidence_not_calibrated",
        bounded_estimate_available: payload.q_records.length >= 3,
        fundamental_spacing_identified: false
      }
    }),
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

export const desktopApi: DesktopApi = window.millikan ?? createDemoApi();
