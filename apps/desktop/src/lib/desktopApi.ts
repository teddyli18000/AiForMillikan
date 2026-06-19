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
  const demoTrackFrame =
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#101820"/><path d="M90 88h110" stroke="#35c9ff" stroke-width="5"/><path d="M90 88v110" stroke="#35c9ff" stroke-width="5"/><text x="210" y="98" font-family="Arial" font-size="32" fill="#35c9ff">+X</text><text x="58" y="230" font-family="Arial" font-size="32" fill="#35c9ff">+Y</text><path d="M570 180 C560 260 590 330 575 430 C565 500 592 560 580 640" stroke="#2563eb" stroke-width="5" fill="none"/><circle cx="580" cy="640" r="18" fill="none" stroke="#22c55e" stroke-width="7"/><text x="606" y="632" font-family="Arial" font-size="32" fill="#22c55e">target</text><text x="36" y="684" font-family="Arial" font-size="28" fill="#ffffff">frame 96  t=3.20s</text></svg>`
    );
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
          air_viscosity_Pa_s: 1.83e-5,
          pressure_kPa: 101.325,
          oil_density_kg_m3: 981,
          cunningham_b_kPa_m: 0.000008226,
          gravity_m_s2: 9.79
        },
        grid: { measurement_distance_m: 0.0015 }
      }
    }),
    normalInspectVideo: async () => ({
      video_path: "raw_data/2.mp4",
      video_url: "demo-normal-video.mp4",
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
      video_url: "demo-normal-video.mp4",
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
          air_viscosity_Pa_s: 1.83e-5,
          pressure_kPa: 101.325,
          oil_density_kg_m3: 981,
          cunningham_b_kPa_m: 0.000008226,
          gravity_m_s2: 9.79
        },
        grid: { measurement_distance_m: 0.0015 }
      }
    };
    },
    normalConfirmBoundary: async (payload) => {
      const fps = demoMetadata.fps || 30;
      const frameCount = demoMetadata.frame_count || 1;
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
        session_root: "runs/normal_demo/session",
        active_video: { state: "boundary_confirmed", boundary },
        session: demoNormalSession()
      };
    },
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
        track_review_frames: Array.from({ length: 10 }, (_, frameIndex) => ({
          frame_index: 40 + frameIndex,
          time_s: 1.4 + frameIndex / 30,
          image_url: demoTrackFrame,
          width: 1280,
          height: 720
        })),
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
      const demoFrame =
        "data:image/svg+xml;utf8," +
        encodeURIComponent(
          `<svg xmlns="http://www.w3.org/2000/svg" width="288" height="288" viewBox="0 0 288 288"><rect width="288" height="288" fill="#101820"/><path d="M144 34v220" stroke="#2563eb" stroke-width="3" fill="none"/><circle cx="144" cy="190" r="18" fill="none" stroke="#22c55e" stroke-width="6"/><text x="166" y="184" font-family="Arial" font-size="24" fill="#22c55e">target</text></svg>`
        );
      const review_frames = Array.from({ length: 8 }, (_, frameIndex) => ({
        frame_index: 52 + frameIndex,
        time_s: 1.72 + frameIndex / 30,
        image_url: demoFrame,
        source_video_box: { x: 96, y: 96, width: 96, height: 96 }
      }));
      const nextEvent = event ? { ...event, review_clip_url: "", review_frames } : undefined;
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
    normalStartNextDroplet: async (payload) => ({
      session_root: "runs/normal_demo/session",
      active_video:
        payload.mode === "same_video"
          ? {
              state: "boundary_confirmed",
              path: "raw_data/2.mp4",
              video_url: "demo-normal-video.mp4",
              metadata: demoMetadata,
              boundary: {
                zero_v_start_s: 0.8,
                zero_v_end_s: 5.13,
                zero_v_start_frame: 24,
                zero_v_end_frame: 154,
                selection_window: { start_s: 0.3, end_s: 1.3, start_frame: 9, end_frame: 39, source: "normal_v1_default" }
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
              }
            }
          : null,
      session: demoNormalSession()
    }),
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
