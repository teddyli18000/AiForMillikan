# 密立根油滴实验

版本 0.9.0。基于平衡电压与零电压下落法，逐滴测量电荷，并从多次测量中估计元电荷。

## 使用流程

1. 导入实验视频，检查画面。
2. 确认零电压区间，可按 1 秒或 0.1 秒微调起止时间。
3. 在零电压起点附近框选油滴，填写平衡电压并确认油滴近似静止。
4. 检查轨迹，逐一复核经过网格线的片段是否为同一颗油滴。
5. 查看电荷、标准不确定度和计算过程，确认保留或返回调整。
6. 保留至少三条有效记录后，估计元电荷。
7. 关闭软件前导出报告；未导出的记录不会留到下次启动。

导出内容包括中文实验报告、测量数据和复核材料。原始 JSON、CSV 保留数值与字段名称，便于后续分析。

## 计算说明

电荷不确定度由速度拟合斜率的不确定度传播得到，未计入仪器与物性参数误差。元电荷通过带不确定度权重的整数倍残差搜索估计；标准值只用于结果对照，不参与搜索。

## 开发与测试

本应用位于 `normal/`，与 `experimental/` 分别维护。内部 Python 包、工作进程接口和数据字段沿用原名。

本地 Python 测试可使用已有的 conda 环境：

```powershell
conda run -n millikan-ai-dev python -m pytest normal/tests -q
cd normal/apps/desktop
npm test
npm run dev
```

Windows 构建与打包由 GitHub Actions 的 Normal CI 完成，覆盖 Python、前端、TypeScript、工作进程、便携版打包及 Electron IPC 检查。安装包名称为 `密立根油滴实验-0.9.0.exe`。发布标签仍使用 `normal-vX.Y.Z`。

## 技术文档

- [前后端接口](docs/frontend_backend_interface.md)
- [测量流程](docs/technical/normal-workflow.md)
- [追踪与复核](docs/technical/tracking-and-review.md)
- [计算方法](docs/academic/)
- [桌面应用开发](docs/desktop_frontend.md)

## 许可

MIT，见 [LICENSE](../LICENSE)。
