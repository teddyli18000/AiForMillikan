import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";
import { desktopApi } from "../src/lib/desktopApi";

async function reachAcceptedNormalRecord() {
  const originalRect = HTMLElement.prototype.getBoundingClientRect;
  const originalPlay = HTMLMediaElement.prototype.play;
  const originalPause = HTMLMediaElement.prototype.pause;
  HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
    return {
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 640,
      bottom: 360,
      width: 640,
      height: 360,
      toJSON: () => ({})
    } as DOMRect;
  };
  HTMLMediaElement.prototype.play = () => Promise.resolve();
  HTMLMediaElement.prototype.pause = () => undefined;

  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /选择视频/ }));
  await userEvent.click(await screen.findByRole("button", { name: /开始处理/ }));
  await userEvent.click(await screen.findByRole("button", { name: /确认边界/ }));

  const overlay = document.querySelector(".normal-video-overlay");
  if (!overlay) throw new Error("normal video overlay not found");
  fireEvent.mouseDown(overlay, { clientX: 120, clientY: 120 });
  fireEvent.mouseMove(overlay, { clientX: 160, clientY: 160 });
  fireEvent.mouseUp(overlay, { clientX: 160, clientY: 160 });

  await userEvent.type(screen.getByPlaceholderText("例如 239"), "239");
  await userEvent.click(screen.getByLabelText(/我确认该油滴/));
  await userEvent.click(screen.getByRole("button", { name: /确认框选并开始追踪/ }));
  await userEvent.click(await screen.findByRole("button", { name: /C001/ }));
  expect(await screen.findByLabelText("过线片段播放器")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /同一颗油滴/ }));
  await userEvent.click(await screen.findByRole("button", { name: "确认保留" }));
  expect(await screen.findByRole("button", { name: /下一颗油滴/ })).toBeInTheDocument();
  expect(await screen.findByLabelText("完整轨迹复核帧播放器")).toBeInTheDocument();
  expect(await screen.findByLabelText("单滴 q 计算流程")).toBeInTheDocument();
  expect(screen.getByText("电荷计算过程")).toBeInTheDocument();

  return () => {
    HTMLElement.prototype.getBoundingClientRect = originalRect;
    HTMLMediaElement.prototype.play = originalPlay;
    HTMLMediaElement.prototype.pause = originalPause;
  };
}

describe("Millikan AI Normal desktop app", () => {
  it("opens the Normal measurement workspace directly", async () => {
    render(<App />);

    expect(await screen.findByRole("button", { name: /选择视频/ })).toBeInTheDocument();
    expect(screen.getAllByText("单滴电荷测量").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /开始处理/ })).toBeDisabled();
    expect(screen.getByText("密立根油滴实验")).toBeInTheDocument();
    expect(screen.getByText("测量流程")).toBeInTheDocument();
    expect(document.querySelector(".normal-progress-box")).toBeNull();
    expect(document.querySelectorAll(".normal-stage small")).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/Normal|workflow|idle|processing|metadata|session/i);
    expect(screen.getByRole("button", { name: "后退 1 秒" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "后退 0.1 秒" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前进 0.1 秒" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前进 1 秒" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /选择视频/ }));
    expect(await screen.findByText("1280 x 720")).toBeInTheDocument();
    expect(screen.getByText("30.00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /开始处理/ }));
    expect(await screen.findByRole("button", { name: /确认边界/ })).toBeInTheDocument();
    expect(screen.getAllByText("确认零电压区间").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /确认边界/ }));
    expect(await screen.findByText("框选时刻（秒）")).toBeInTheDocument();
    expect(screen.getAllByText("框选油滴").length).toBeGreaterThan(0);
    expect(screen.getByText("允许范围：0.30 - 1.30 s")).toBeInTheDocument();
    expect(document.querySelector(".normal-selection-preview")).toBeNull();
  });

  it("shows progress only while processing and uses Chinese frame units", async () => {
    const prepare = desktopApi.normalPrepareVideo;
    let finish!: () => void;
    const gate = new Promise<void>((resolve) => { finish = resolve; });
    const spy = vi.spyOn(desktopApi, "normalPrepareVideo").mockImplementation(async (payload) => {
      const result = await prepare(payload);
      await gate;
      return result;
    });
    try {
      render(<App />);
      await userEvent.click(await screen.findByRole("button", { name: "选择视频" }));
      await userEvent.click(screen.getByRole("button", { name: "开始处理" }));
      expect(await screen.findByText("正在采样电压显示区域")).toBeInTheDocument();
      expect(screen.getByRole("progressbar", { name: "处理进度" })).toHaveAttribute("aria-valuenow", "30");
      expect(screen.getByText("30% · 12 / 40 帧")).toBeInTheDocument();
      await act(async () => { finish(); });
      expect(await screen.findByRole("button", { name: "确认边界" })).toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).toBeNull();
    } finally {
      finish();
      spy.mockRestore();
    }
  });

  it("reports a successful export correctly", async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "导出报告" }));
    expect(await screen.findByText("实验记录已导出。")).toBeInTheDocument();
  });

  it("reviews crossing frames and starts the next droplet in the same video", async () => {
    const cleanupRect = await reachAcceptedNormalRecord();
    try {
      await userEvent.click(screen.getByRole("button", { name: /下一颗油滴/ }));
      expect(await screen.findByRole("dialog", { name: /下一颗油滴/ })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /同一个视频/ }));
      expect(await screen.findByText("框选时刻（秒）")).toBeInTheDocument();
      expect(screen.getByText("在视频画面上拖拽一个矩形包住油滴")).toBeInTheDocument();
      const overlay = document.querySelector(".normal-video-overlay");
      if (!overlay) throw new Error("normal video overlay not found for second droplet");
      fireEvent.mouseDown(overlay, { clientX: 180, clientY: 140 });
      fireEvent.mouseMove(overlay, { clientX: 220, clientY: 180 });
      fireEvent.mouseUp(overlay, { clientX: 220, clientY: 180 });
      await userEvent.click(screen.getByRole("button", { name: /确认框选并开始追踪/ }));
      await userEvent.click(await screen.findByRole("button", { name: /C001/ }));
      expect(await screen.findByLabelText("过线片段播放器")).toBeInTheDocument();
    } finally {
      cleanupRect();
    }
  });

  it("starts the next droplet with a new video without clearing accepted q records", async () => {
    const cleanupRect = await reachAcceptedNormalRecord();
    try {
      await userEvent.click(screen.getByRole("button", { name: /下一颗油滴/ }));
      await userEvent.click(await screen.findByRole("button", { name: /换一个视频/ }));
      expect(await screen.findByPlaceholderText("拖入视频或粘贴绝对路径")).toHaveValue("");
      expect(screen.getByText(/共 \d+ 条，已保留 \d+ 条/)).toBeInTheDocument();
    } finally {
      cleanupRect();
    }
  });

  it("opens a dedicated Normal inversion result page after three accepted q records", async () => {
    const cleanupRect = await reachAcceptedNormalRecord();
    async function acceptNextDroplet(x: number) {
      await userEvent.click(screen.getByRole("button", { name: /下一颗油滴/ }));
      await userEvent.click(await screen.findByRole("button", { name: /同一个视频/ }));
      const overlay = document.querySelector(".normal-video-overlay");
      if (!overlay) throw new Error("normal video overlay not found for inversion test");
      fireEvent.mouseDown(overlay, { clientX: x, clientY: 130 });
      fireEvent.mouseMove(overlay, { clientX: x + 36, clientY: 170 });
      fireEvent.mouseUp(overlay, { clientX: x + 36, clientY: 170 });
      await userEvent.click(screen.getByRole("button", { name: /确认框选并开始追踪/ }));
      await userEvent.click(await screen.findByRole("button", { name: /C001/ }));
      await userEvent.click(await screen.findByRole("button", { name: /同一颗油滴/ }));
      await userEvent.click(await screen.findByRole("button", { name: "确认保留" }));
      expect(await screen.findByRole("button", { name: /下一颗油滴/ })).toBeInTheDocument();
    }
    try {
      await acceptNextDroplet(180);
      await acceptNextDroplet(240);
      await userEvent.click(screen.getAllByRole("button", { name: "估计元电荷" }).at(-1)!);
      expect(await screen.findByLabelText("元电荷结果页")).toBeInTheDocument();
      expect(screen.getAllByText("元电荷估计").length).toBeGreaterThan(0);
      expect(screen.getByText("标准不确定度 σe")).toBeInTheDocument();
      expect(screen.getByText("相对不确定度")).toBeInTheDocument();
      expect(screen.getByText("与标准值的相对误差")).toBeInTheDocument();
      expect(screen.getByText("候选解")).toBeInTheDocument();
      expect(screen.getByText("整数分配与残差")).toBeInTheDocument();
      expect(screen.getByRole("img", { name: "归一化残差图" })).toBeInTheDocument();
      expect(screen.queryByText(/模型胜出|quantized_favored|continuous_favored/)).toBeNull();
      expect(document.body.textContent).not.toMatch(/\d(?:\.\d+)?e[+-]\d+/i);
      expect(document.body.textContent).not.toMatch(/Normal|accepted|stable|boundary|baseline|flags|session|backend/i);
    } finally {
      cleanupRect();
    }
  });
});
