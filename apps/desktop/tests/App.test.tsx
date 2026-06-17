import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";

describe("Millikan desktop app", () => {
  it("opens from splash into the setup workspace", async () => {
    render(<App />);

    expect(screen.getByText("从实验视频盲反演元电荷")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /进入分析工作台/ }));

    expect(await screen.findByText("单滴平衡-下落测量")).toBeInTheDocument();
    expect(screen.getByText(/最终报告前可用 q/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成 q 记录/ })).toBeInTheDocument();
  });

  it("keeps experimental mode available and shows readable math", async () => {
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: /进入分析工作台/ }));
    await userEvent.click(await screen.findByRole("button", { name: /切到 Experimental/ }));
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

    await userEvent.click(screen.getByRole("button", { name: /进入分析工作台/ }));
    await userEvent.click(await screen.findByRole("button", { name: /打开视频/ }));
    await userEvent.click(await screen.findByText(/点击画面标注油滴中心/));
    await userEvent.click(screen.getByRole("button", { name: /建议边界/ }));
    await userEvent.click(screen.getByRole("button", { name: /生成 q 记录/ }));

    expect(await screen.findByText("普通模式结果", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/最终报告导出前，当前可用于盲反演的 q 记录数为 1/)).toBeInTheDocument();
  });
});
