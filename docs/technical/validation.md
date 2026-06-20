# 测试与复现

## 自动测试层次

### Python

```powershell
.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp_work -o cache_dir=runs\pytest_cache_work
```

覆盖视频/网格、Normal session 状态、selection window、目标帧、追踪、crossing 阻断、q 计算、不确定度、盲反演、Experimental pipeline 和 artifact contract。

### Frontend

```powershell
cd apps\desktop
npm test -- --run
npm run build
```

覆盖 Normal/Experimental 导航、秒级播放器、框选几何、返回修改、下一颗、复核播放器、q 流程、反演结果和科学计数格式。

### Encoding

```powershell
.venv\Scripts\python scripts\check_text_encoding.py
```

编码测试还会强制父进程使用 legacy codepage，并拆分中文 UTF-8 字节，证明 producer 和 consumer 都不会依赖 Windows 默认代码页。

## Packaged 验收

正式包使用：

```text
C:\Users\Teddy\Desktop\追踪\raw_videos\test.mp4
```

验收路径：

```text
导入 → 预览 → 开始处理 → 0 V 边界 → 框选
→ tracking → crossing/轨迹复核 → q → 用户接受
→ session 累积 → 盲反演 → 导出
```

如果真实视频没有足够 crossing，使用自动测试生成的 crossing synthetic video 验证：

- 未复核不能接受；
- `different_drop` 不能进入反演；
- 全部 `same_drop` 后才可继续。

## 科学验证与产品验收的区别

真实视频用于验证软件流程、坐标、可播放证据和用户交互，不用于宣称元电荷估计达到某一精度。数值算法验证使用已知真值的 synthetic fixtures，并明确样本量、噪声和容差。

Normal 三条 accepted q 只能给出探索性反演结果。没有真实 continuous baseline 时，不报告量子化模型胜出。
