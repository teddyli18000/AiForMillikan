# Millikan AI 1.0 文档

本目录区分当前实现、学术说明和历史材料，避免早期方案与正式版 contract 混在一起。

## 技术文档

- [系统架构](technical/architecture.md)：Electron、React、Python worker、Normal 与 Experimental 的边界。
- [Normal 工作流与状态机](technical/normal-workflow.md)：五阶段用户流程、session、record 和 worker 前置状态。
- [追踪坐标与人工复核](technical/tracking-and-review.md)：矩形框选、视频坐标、Trackpy、crossing 和整轨迹证据。
- [UTF-8、构建与发布](technical/encoding-build-release.md)：Windows 管道编码、PyInstaller、Electron packaging 和 Release。
- [测试与复现](technical/validation.md)：自动测试、真实视频验收和科学验证边界。
- [完整前后端接口](frontend_backend_interface.md)：机器可读 artifact 与 IPC contract。
- [桌面开发说明](desktop_frontend.md)：本地开发、测试和打包命令。

## 学术文档

- [实验方法](academic/experiment-method.md)：平衡电压与 `0 V` 下落的物理前提。
- [单滴电荷计算](academic/charge-measurement.md)：从轨迹速度到 Cunningham 修正半径与 `q`。
- [不确定度](academic/uncertainty.md)：线性拟合斜率不确定度和当前纳入/未纳入项。
- [元电荷盲反演](academic/blind-inversion.md)：整数分配、加权重估、候选解与探索性结论。
- [科学边界](academic/scientific-boundaries.md)：AI 的角色、有效证据和不能宣称的结论。

## 版本与历史

- [版本修复记录](版本修复记录.md)：Normal `0.1.1` 至 `1.0.0` 的 contract 演进。
- [真实视频 smoke 记录](raw_video_smoke.md)：历史 raw-video 行为记录。
- [archive](archive/)：早期长文、失败路线和未交付研究设想。仅用于追溯，不代表 1.0 当前实现。

## 阅读建议

首次使用者从根目录 [README](../README.md) 开始。需要复现实验时阅读“实验方法”和“测试与复现”；需要开发或审查 contract 时阅读“系统架构”“Normal 工作流”与“完整前后端接口”。
