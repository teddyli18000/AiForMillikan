import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";

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
  await userEvent.click(screen.getByRole("button", { name: /Normal/ }));
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
  expect(await screen.findByLabelText("crossing 局部复核帧播放器")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /同一颗油滴/ }));
  await userEvent.click(await screen.findByRole("button", { name: "确认保留" }));
  expect(await screen.findByRole("button", { name: /下一颗油滴/ })).toBeInTheDocument();

  return () => {
    HTMLElement.prototype.getBoundingClientRect = originalRect;
    HTMLMediaElement.prototype.play = originalPlay;
    HTMLMediaElement.prototype.pause = originalPause;
  };
}

describe("Millikan desktop app", () => {
  it("opens Normal as the recommended measurement workspace", async () => {
    render(<App />);

    expect(screen.getByText("人机协同测量油滴电荷，盲反演元电荷")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Normal/ }));

    expect(await screen.findByRole("button", { name: /选择视频/ })).toBeInTheDocument();
    expect(screen.getAllByText("平衡电压 + 0V 下落逐滴测量").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /开始处理/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "后退 1 秒" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "后退 0.1 秒" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前进 0.1 秒" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前进 1 秒" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /选择视频/ }));
    expect(await screen.findByText("1280 x 720")).toBeInTheDocument();
    expect(screen.getByText("30.00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /开始处理/ }));
    expect(await screen.findByRole("button", { name: /确认边界/ })).toBeInTheDocument();
    expect(screen.getAllByText("0V 边界确认").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /确认边界/ }));
    expect(await screen.findByText("selection time (s)")).toBeInTheDocument();
    expect(screen.getAllByText("框选目标油滴").length).toBeGreaterThan(0);
    expect(screen.getByText("允许范围：0.30 - 1.30 s")).toBeInTheDocument();
    expect(document.querySelector(".normal-selection-preview")).toBeNull();
  });

  it("keeps the Experimental demo analysis path available", async () => {
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: /Experimental/ }));

    expect(await screen.findByText("拖入实验视频")).toBeInTheDocument();
    expect(screen.getAllByText("平台设置").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /开始分析/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回模式选择" }));
    expect(await screen.findByRole("button", { name: /Normal/ })).toBeInTheDocument();
  });

  it("reviews crossing frames and starts the next droplet in the same video", async () => {
    const cleanupRect = await reachAcceptedNormalRecord();
    try {
      await userEvent.click(screen.getByRole("button", { name: /下一颗油滴/ }));
      expect(await screen.findByRole("dialog", { name: /下一颗油滴/ })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /同一个视频/ }));
      expect(await screen.findByText("selection time (s)")).toBeInTheDocument();
      expect(screen.getByText("在视频画面上拖拽一个矩形包住油滴")).toBeInTheDocument();
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
      expect(screen.getByText(/accepted/)).toBeInTheDocument();
    } finally {
      cleanupRect();
    }
  });

  it("runs the demo analysis path and shows elementary-charge diagnostics", async () => {
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: /Experimental/ }));
    await userEvent.click(await screen.findByRole("button", { name: /打开文件/ }));
    expect(await screen.findByText("1280 × 720")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /开始分析/ }));
    expect(await screen.findByText("数学推导", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/q_i ≈ n_i e/)).toBeInTheDocument();
    expect(screen.getByText("证据强度")).toBeInTheDocument();
  });
});
