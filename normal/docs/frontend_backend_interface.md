# Normal 前后端接口

本文定义 Normal 桌面界面、Electron IPC 与 Python worker 之间的接口。worker 位于 `normal/src/millikan_ai/desktop_worker.py`，只接收下表中的十二个 `normal.*` 操作。

## 传输与路由

worker 通过 UTF-8、无 BOM 的 JSON Lines 收发请求。每条请求包含 `id`、`op` 和 `payload`；回复类型为 `result`、`error` 或 `progress`。

preload 调用冒号分隔的 Electron channel；`electron/main.ts` 将其映射到点分隔的 worker 操作。两种名称属于不同边界。

| preload 方法 | Electron channel | worker 操作 |
| --- | --- | --- |
| `normalInitialize` | `normal:initialize` | `normal.initialize` |
| `normalInspectVideo` | `normal:inspectVideo` | `normal.inspectVideo` |
| `normalPrepareVideo` | `normal:prepareVideo` | `normal.prepareVideo` |
| `normalConfirmBoundary` | `normal:confirmBoundary` | `normal.confirmBoundary` |
| `normalSelectTarget` | `normal:selectTarget` | `normal.selectTarget` |
| `normalSaveMeasurement` | `normal:saveMeasurement` | `normal.saveMeasurement` |
| `normalPrepareCrossingReview` | `normal:prepareCrossingReview` | `normal.prepareCrossingReview` |
| `normalReviewCrossing` | `normal:reviewCrossing` | `normal.reviewCrossing` |
| `normalSelectRecord` | `normal:updateRecordSelection` | `normal.updateRecordSelection` |
| `normalStartNextDroplet` | `normal:startNextDroplet` | `normal.startNextDroplet` |
| `normalRunInversion` | `normal:runInversion` | `normal.runInversion` |
| `normalExportSession` | `normal:exportSession` | `normal.exportSession` |

`normalPrepareVideo`、`normalSaveMeasurement` 和 `normalRunInversion` 可发出进度。main 将 worker 进度转发为 `normal:progress`，preload 的 `onNormalProgress` 订阅该 channel 并返回取消订阅函数。

其他 preload 能力：`openVideoDialog` 返回所选视频路径或 `null`；`getDroppedFilePath` 使用 Electron `webUtils` 读取拖入文件路径。这两项不调用 worker。

## 会话与状态

- 不传 `session_root` 调用 `normal.initialize` 会创建新会话；传入已有会话目录时会读取其中的 `normal_session.json`。
- Electron 只在退出时清理由应用隐式创建的临时会话目录。用户通过导出保存需要保留的实验。
- 一个会话可跨多个视频累积记录。各操作返回的 `session_root` 应传给后续 worker 操作。
- `normal.inspectVideo` 只读取视频元数据和可播放 URL，不创建或修改会话。

视频状态为 `video_prepared`、`boundary_confirmed`、`target_selected`、`tracking`。记录状态为 `pending_crossing_review`、`pending_user_confirmation`、`accepted`、`diagnostic`、`rejected_crossing_identity`、`rejected_by_user`。worker 校验操作前置状态；界面按钮禁用不能代替该校验。

```text
导入并检查视频 → 准备视频 → 确认零电压区间 → 选择油滴 → 测量
→ 轨迹复核 → 用户确认并保留
```

诊断记录、身份复核未通过的记录和用户排除的记录仍保存在本次会话中，但不参与反演。调整旧记录会创建新记录，并通过 `retry_of_record_id` 指向原记录。

## 视频、边界与目标选择

- `normal.prepareVideo` 检查视频、建议零电压区间并检测网格，返回视频元数据、区间、网格标定和有效测量区。
- `normal.confirmBoundary` 接收 `boundary.zero_v_start_s` 与 `boundary.zero_v_end_s`。秒数是权威值；worker 依据 FPS 重新计算帧号和目标选择窗口。
- 所有用户时间输入与显示使用秒。帧号用于视频定位和记录溯源。
- 默认目标选择窗口以用户确认的 `zero_v_start_s` 为中心，前后各 0.5 秒，并裁剪到视频时长范围。界面和 worker 都必须限制在此窗口内。
- `normal.selectTarget` 要求正的 `balance_voltage_V` 和 `balance_confirmed: true`；目标包含 `target_frame` 或 `target_time_s`，以及源视频坐标下的 `source_center`、`source_video_box`。
- 目标时间、播放器画面与提交的目标帧必须一致。追踪从实际选中的帧开始。

视频坐标原点在左上角，X 向右、Y 向下；`time_s = frame_idx / fps`。界面播放器坐标必须先换算为源视频坐标再提交。

## 测量记录与轨迹复核

`normal.saveMeasurement` 需要已选目标状态；worker 单独追踪一颗油滴，拟合零电压下落速度并计算电荷。记录保留视频与时间窗口、目标框、网格、实际参数、轨迹、过线事件、拟合、q 结果和状态。

常用记录字段：`record_id`、`retry_of_record_id`、`video_path`、`balance_voltage_V`、`time_window`、`target`、`grid`、`tracking`、`crossing_events`、`fit`、`q`、`status`、`kept`。`q` 包含 `valid`、`q_C`、`sigma_q_C`、`radius_m`、`flags` 与 `calculation_trace`。worker 的公开记录还提供 `track_review_frames`、过线事件和证据路径。

`normal.prepareCrossingReview` 按需生成并返回所选事件的复核帧和可播放 URL。`normal.reviewCrossing` 只接受 `same_drop` 或 `different_drop`：

- 所有过线事件均复核为 `same_drop` 后，合格记录进入 `pending_user_confirmation`。
- `different_drop` 将记录设为 `rejected_crossing_identity`，不能保留或参与反演。
- `normal.updateRecordSelection` 用 `kept: true` 确认合格记录；用 `kept: false` 排除记录。排除只改变记录状态，不删除测量证据。

`normal.startNextDroplet` 的 `mode` 为 `same_video` 或 `different_video`。前者恢复当前视频的边界确认状态；后者清空 `active_video`，保留会话记录。

## 参数与单滴电荷

`normal.initialize` 返回后端配置。平衡电压必须由用户确认；高级参数通过当前测量的 `parameter_overrides` 提交，界面应只提交用户修改的值。压力字段使用 `pressure_kPa`。

q 由平衡电压与零电压下落速度计算；`sigma_q_C` 由速度拟合误差传播得到。`calculation_trace` 提供计算实际使用的输入和中间量。界面可以格式化并展示计算过程，不得根据局部状态重新计算权威物理结果。

无效拟合或电荷结果以 `diagnostic` 记录返回，不得作为已保留结果参与反演。机器数据使用 SI 数值；显示时可格式化为 `1.602 × 10⁻¹⁹ C`。

## 元电荷反演

`normal.runInversion` 只使用已保留、状态为 `accepted`、q 与不确定度为有限正值且过线身份复核通过的记录。默认至少需要三条记录。

反演结果包含 `status`、`e_hat_C`、`sigma_e_C`、`valid_q_count`、`flags`、`assignments`、`candidates`、`charts` 与 `reference_comparison`。记录不足时返回 `insufficient_eligible_records`。正好三条记录时标记为探索性结果。

`reference_comparison` 用于结果展示，不参与候选搜索、排序或整数分配。Normal 当前没有连续基线模型，不得声称模型胜出。

保留或排除记录、过线身份复核未通过后，清除已有反演结果；界面和导出报告须使用重新计算的结果。

## 导出

`normal:exportSession` 先通过 Electron 目录选择器获取导出位置，再调用 worker 的 `normal.exportSession`。取消选择时 main 返回 `{ canceled: true }`；成功时返回 `{ canceled: false, destination, package }`，其中 `package` 是 worker 的结果。

worker 在所选目录下创建 `<session_id>_export/`，包括：

- `normal_session_report.md`：中文测量报告；
- `normal_session.json`：会话与记录数据；
- `records/`：有测量记录时包含的测量与复核证据；
- `normal_inversion.json`：已运行反演时的结果；
- `export_manifest.json`：导出文件清单。

worker 返回导出子目录、清单和 Markdown 报告路径。
