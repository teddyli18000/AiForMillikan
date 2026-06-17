import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DesktopApi } from "../src/types";

const metadata = {
  path: "C:/videos/test.mp4",
  readable: true,
  width: 240,
  height: 180,
  fps: 30,
  frame_count: 90,
  duration_s: 3
};

function installMockApi(overrides: Partial<DesktopApi> = {}) {
  const listeners: Array<(event: { percent: number; label: string }) => void> = [];
  let qIndex = 0;
  const api: DesktopApi = {
    openVideoDialog: vi.fn(async () => "C:/videos/test.mp4"),
    openRunDialog: vi.fn(async () => null),
    inspectVideo: vi.fn(async () => ({ metadata })),
    detectPlatformBoundaries: vi.fn(async () => ({ diagnostics: {}, suggestions: [], samples: [] })),
    runAnalysis: vi.fn(),
    runAutoAnalysis: vi.fn(),
    loadRun: vi.fn(),
    validateRun: vi.fn(),
    runDownstream: vi.fn(),
    exportReport: vi.fn(async () => ({ canceled: false })),
    openPath: vi.fn(),
    suggestNormalV2Window: vi.fn(async () => ({
      window: { start_frame: 30, end_frame: 75, start_time_s: 1, end_time_s: 2.5, flags: ["has_recovery_operation"] },
      operations: [{ start_frame: 20, end_frame: 24, peak_score: 0.8 }]
    })),
    runNormalV2SingleDrop: vi.fn(async () => {
      qIndex += 1;
      return {
      q_record: {
        record_id: `q_mock_00${qIndex}`,
        video_path: "C:/videos/test.mp4",
        target_frame: 30,
        window: { start_frame: 30, end_frame: 75 },
        q_C: 3.2e-19,
        sigma_q_C: 0.1e-19,
        valid: true,
        selected: true,
        flags: [],
        run_dir: "runs/normal"
      },
      track_points: [
        { frame_idx: 30, time_s: 1, status: "tracking", x: 70, y: 55, predicted_x: 70, predicted_y: 55 },
        { frame_idx: 31, time_s: 1.033, status: "missing", x: null, y: null, predicted_x: 70, predicted_y: 56 },
        { frame_idx: 32, time_s: 1.066, status: "reacquired", x: 70, y: 57, predicted_x: 70, predicted_y: 57 }
      ],
      events: [{ type: "missing_reacquired", missing_start_frame: 31, reacquired_frame: 32 }],
      files: {}
    };
    }),
    saveNormalV2Session: vi.fn(async ({ records }) => ({ counts: { total: records.length, valid: records.length, selected_valid: records.length }, session: { records } })),
    loadNormalV2Session: vi.fn(),
    estimateNormalV2Elementary: vi.fn(async () => ({
      normal_algorithm: { valid: true, e_hat_C: 1.602e-19, status: "ok" },
      experimental_algorithm: { bounded_estimate_available: true, quantization_supported: false, status: "bounded_estimate_evidence_not_calibrated" }
    })),
    writeNormalV2SessionReport: vi.fn(),
    onAnalysisProgress: (callback) => {
      listeners.push(callback);
      return () => undefined;
    },
    ...overrides
  } as DesktopApi;
  window.millikan = api;
  return api;
}

async function loadApp() {
  vi.resetModules();
  const module = await import("../src/App");
  return module.default;
}

describe("Millikan desktop app normal mode", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    delete window.millikan;
  });

  afterEach(() => {
    delete window.millikan;
  });

  it("shows an integration error instead of demo data when preload is missing", async () => {
    const App = await loadApp();
    render(<App />);

    expect(screen.getByText(/桌面集成不可用/)).toBeInTheDocument();
    expect(screen.queryByText(/3.2e-19/)).not.toBeInTheDocument();
  });

  it("keeps the simple normal-mode flow on one screen", async () => {
    installMockApi();
    const App = await loadApp();
    render(<App />);

    await waitFor(() => expect(screen.getAllByText("普通模式").length).toBeGreaterThan(0));
    expect(screen.getByRole("button", { name: /打开视频/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成时间建议/ })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /打开视频/ }));
    expect(await screen.findByText("240 × 180")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成时间建议/ })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("平衡电压"));
    await userEvent.type(screen.getByLabelText("平衡电压"), "240");
    expect(screen.getByRole("button", { name: /生成时间建议/ })).toBeEnabled();
  });

  it("seeks the player after suggestion, stores target frame, saves q, and switches algorithms", async () => {
    const api = installMockApi();
    const App = await loadApp();
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /打开视频/ }));
    await userEvent.clear(screen.getByLabelText("平衡电压"));
    await userEvent.type(screen.getByLabelText("平衡电压"), "240");
    await userEvent.click(screen.getByRole("button", { name: /生成时间建议/ }));

    const video = await screen.findByTestId("normal-video-player") as HTMLVideoElement;
    await waitFor(() => expect(video.currentTime).toBe(1));

    await userEvent.click(screen.getByRole("button", { name: /框选当前油滴/ }));
    expect(screen.getByText(/target_frame: 30/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /运行追踪/ }));
    expect(await screen.findByText("q_mock_001")).toBeInTheDocument();
    expect(api.saveNormalV2Session).toHaveBeenCalled();
    expect(screen.getAllByText(/tracking/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/missing/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/reacquired/).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: /运行追踪/ }));
    await screen.findByText("q_mock_002");
    await userEvent.click(screen.getByRole("button", { name: /运行追踪/ }));
    await screen.findByText("q_mock_003");

    await userEvent.click(screen.getByRole("button", { name: /运行双算法/ }));
    expect(await screen.findByText(/Normal e/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Experimental 算法/ }));
    expect(screen.getByText(/bounded_estimate_evidence_not_calibrated/)).toBeInTheDocument();
  });
});
