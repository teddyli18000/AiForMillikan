# 追踪坐标与人工复核

## 选择帧与矩形框

用户在主视频播放器中选择 `selection_time_s`。显示帧、前端时间和提交给 backend 的 `target_frame` 必须是同一帧。

矩形框坐标映射只针对实际视频内容区域。HTML `<video>` 在 `object-fit: contain` 下可能存在 letterbox，映射过程必须：

1. 读取视频原始宽高与元素显示宽高；
2. 计算保持宽高比后的 content box；
3. 扣除左右或上下黑边；
4. 将 pointer 坐标限制在 content box；
5. 按原始视频像素比例生成矩形。

任何叠加证据都使用原视频像素坐标，不能按整个 DOM 元素尺寸直接缩放。

## Normal 单滴 Trackpy

Normal 内部复制并封装了队友验证的局部单滴思路，不直接 import 外部项目。当前关键参数来自 `DEFAULT_NORMAL_CONFIG`：

| 参数 | 1.0 默认值 |
|---|---:|
| `diameter` | 5 |
| `minmass` | 80 |
| `local_search_radius_px` | 45 |
| `max_accept_distance_px` | 30 |
| `memory_frames` | 5 |
| `local_topn` | 20 |

追踪从实际框选帧开始。每帧根据上次检测与速度预测位置，仅在局部窗口运行 Trackpy；候选超过最大接受距离则记为 missing。短暂丢失后允许 reacquired，超过 memory 后停止。

## 后端证据

每条记录生成：

- `track.csv`
- `crossing_events.json`
- `visualization_layers.json`
- `overlay_review.mp4`
- `track_review_frames/`

整轨迹 review frame 在原始视频帧上绘制真实 target/missing、轨迹、时间、帧号和像素坐标轴。前端只播放这些图片。

## Crossing review

crossing 来源包括网格附近 missing/reacquired 和几何跨线事件。用户点击事件后，backend 读取事件前后约一秒的原视频：

- 围绕真实轨迹位置裁剪；
- 在裁剪图中绘制 target/missing 与局部轨迹；
- 放大并保存 `review_frames`；
- 在视频首尾自动裁剪时间范围。

未复核 crossing 会阻断 acceptance。任意 `different_drop` 将记录置为 `rejected_crossing_identity`；只有全部 `same_drop` 才能进入用户最终确认。

## 为什么由后端绘制

浏览器与视频元素存在缩放、DPI、letterbox 和响应式布局。把坐标绘制放在前端会重新引入错位风险。后端在原视频像素上生成证据，保证导出文件、UI 和科学记录引用同一坐标来源。
