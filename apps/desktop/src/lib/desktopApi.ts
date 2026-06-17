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
