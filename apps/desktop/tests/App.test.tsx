import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";

describe("Millikan desktop app", () => {
  it("keeps the splash animation and enters normal mode by default choice", async () => {
    render(<App />);

    expect(screen.getByText("从实验视频盲反演元电荷")).toBeInTheDocument();
    expect(document.querySelector(".oil-particle")).toBeTruthy();
    expect(await screen.findByRole("button", { name: /普通模式/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /普通模式/ }));

    expect(await screen.findByText("Normal balance-fall mode")).toBeInTheDocument();
    expect(await screen.findByText("导入视频并输入平衡电压")).toBeInTheDocument();
    expect(screen.queryByText("盲反演结果")).not.toBeInTheDocument();
  });

  it("keeps Experimental behind risk confirmation and preserves setup flow", async () => {
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /Experimental/ }));
    expect(await screen.findByText("进入 Experimental 前请确认")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /我了解风险/ }));

    expect(await screen.findByText("拖入实验视频")).toBeInTheDocument();
    expect(screen.getAllByText("平台设置").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /开始分析/ })).toBeInTheDocument();
  });

  it("normal mode uses progressive disclosure and explicit mocks only in tests", async () => {
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /普通模式/ }));
    expect(await screen.findByText("导入视频并输入平衡电压")).toBeInTheDocument();
    expect(screen.queryByText("跨网格片段")).not.toBeInTheDocument();
    expect(screen.queryByText("已保存 q 记录")).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("普通模式视频路径"), "raw_data/2.mp4");
    await userEvent.click(screen.getByRole("button", { name: /生成时间建议/ }));
    expect(await screen.findByText("检查建议时间")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /确认时间，框选油滴/ })).toBeInTheDocument();
  });
});
