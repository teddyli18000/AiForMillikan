import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";

describe("Millikan desktop app", () => {
  it("opens from splash into the setup workspace", async () => {
    render(<App />);

    expect(screen.getByText("从实验视频盲反演元电荷")).toBeInTheDocument();
    await enterNormalMode();

    expect(await screen.findByText("单滴平衡-下落测量")).toBeInTheDocument();
    expect(screen.getByText(/最终报告前可用 q/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成 q 记录/ })).toBeInTheDocument();
  });

  it("keeps experimental mode available and shows readable math", async () => {
    render(<App />);

    const experimentalButton = await screen.findByRole("button", { name: /Experimental多滴探索/ }, { timeout: 4000 });
    await waitFor(() => expect(experimentalButton).toBeEnabled(), { timeout: 4000 });
    await userEvent.click(experimentalButton);
    const enterButton = await screen.findByRole("button", { name: /进入Experimental/ }, { timeout: 4000 });
    await waitFor(() => expect(enterButton).toBeEnabled(), { timeout: 4000 });
    await userEvent.click(enterButton);
    expect(await screen.findByText("Experimental 多滴流程")).toBeInTheDocument();
    expect(screen.getByText("拖入实验视频")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /打开文件/ }));
    expect(await screen.findByText("1280 × 720")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /开始分析/ }));
    expect(await screen.findByText("数学推导", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText(/q_i/)).not.toBeInTheDocument();
    expect(screen.queryByText(/y_0|v_g|η_eff|fundamental_spacing_identified/)).not.toBeInTheDocument();
    expect(screen.getByText("证据强度")).toBeInTheDocument();
  });

  it("runs the normal demo path and tracks usable q count dynamically", async () => {
    render(<App />);

    await enterNormalMode();
    await userEvent.click(await screen.findByRole("button", { name: /打开视频/ }));
    selectNormalTarget();
    await userEvent.click(screen.getByRole("button", { name: /建议边界/ }));
    await userEvent.click(screen.getByRole("button", { name: /生成 q 记录/ }));

    expect(await screen.findByText("普通模式结果", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/最终报告导出前，当前可用于盲反演的 q 记录数为 1/)).toBeInTheDocument();
  });

  it("keeps results placeholders empty before any analysis", async () => {
    render(<App />);

    await enterNormalMode();
    await userEvent.click(screen.getByRole("button", { name: /元电荷诊断/ }));

    expect(await screen.findByText("估计 e")).toBeInTheDocument();
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
    expect(screen.queryByText(/1\.604/)).not.toBeInTheDocument();
  });
});

async function enterNormalMode() {
  const enterButton = await screen.findByRole("button", { name: /进入普通模式/ }, { timeout: 4000 });
  await waitFor(() => expect(enterButton).toBeEnabled(), { timeout: 4000 });
  await userEvent.click(enterButton);
  await screen.findByText("单滴平衡-下落测量");
}

function selectNormalTarget() {
  const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
    if ((this as HTMLElement).dataset.testid === "normal-video-shell") {
      return {
        x: 0,
        y: 0,
        left: 0,
        top: 0,
        width: 960,
        height: 540,
        right: 960,
        bottom: 540,
        toJSON: () => undefined
      } as DOMRect;
    }
    return originalGetBoundingClientRect.call(this);
  };
  const shell = screen.getByTestId("normal-video-shell");
  fireEvent.pointerDown(shell, { clientX: 210, clientY: 140, pointerId: 1 });
  fireEvent.pointerMove(shell, { clientX: 260, clientY: 190, pointerId: 1 });
  fireEvent.pointerUp(shell, { clientX: 260, clientY: 190, pointerId: 1 });
  HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
}
