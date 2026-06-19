import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";

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
