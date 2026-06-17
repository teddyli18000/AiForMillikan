import { useMemo, useRef, useState } from "react";
import type { DragEvent, PointerEvent } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  Calculator,
  CheckCircle2,
  CircleDot,
  FileVideo,
  FlaskConical,
  Gauge,
  MousePointer2,
  Play,
  Search,
  Target,
  TimerReset,
  ToggleLeft,
  ToggleRight
} from "lucide-react";
import type { NormalElementaryEstimate, NormalQRecord, NormalTarget, NormalWindow, VideoMetadata } from "../types";
import { fmtCharge, fmtNumber } from "../lib/format";

type NormalSetupViewProps = {
  videoPath: string;
  metadata: VideoMetadata | null;
  balanceVoltage: number;
  target: NormalTarget | null;
  window: NormalWindow | null;
  qRecords: NormalQRecord[];
  elementary: NormalElementaryEstimate | null;
  isRunning: boolean;
  onOpenVideo: () => void;
  onVideoPath: (path: string) => void;
  onInspect: (path?: string) => void;
  onVideoDrop: (path: string) => void;
  onBalanceVoltage: (value: number) => void;
  onTarget: (target: NormalTarget) => void;
  onSuggestWindow: () => void;
  onWindow: (window: NormalWindow) => void;
  onRun: () => void;
  onToggleRecord: (recordId: string) => void;
  onEstimate: () => void;
  onUseExperimental: () => void;
};

export function NormalSetupView({
  videoPath,
  metadata,
  balanceVoltage,
  target,
  window,
  qRecords,
  elementary,
  isRunning,
  onOpenVideo,
  onVideoPath,
  onInspect,
  onVideoDrop,
  onBalanceVoltage,
  onTarget,
  onSuggestWindow,
  onWindow,
  onRun,
  onToggleRecord,
  onEstimate,
  onUseExperimental
}: NormalSetupViewProps) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef<{ clientX: number; clientY: number } | null>(null);
  const [selection, setSelection] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const usableSelectedCount = qRecords.filter((record) => record.selected !== false && record.usable_for_inversion).length;
  const selectedCount = qRecords.filter((record) => record.selected !== false).length;
  const videoSrc = useMemo(() => toFileUrl(videoPath), [videoPath]);
  const duration = metadata?.duration_s ?? 0;
  const fps = metadata?.fps && metadata.fps > 0 ? metadata.fps : 30;
  const startTime = window ? window.fall_start_frame / fps : 0;
  const endTime = window?.fall_end_frame != null ? window.fall_end_frame / fps : duration;

  const setBoundary = (which: "start" | "end", deltaS: number) => {
    const current: NormalWindow = window ?? {
      fall_start_frame: 0,
      fall_end_frame: metadata ? Math.max(0, metadata.frame_count - 1) : 0
    };
    const maxFrame = metadata ? Math.max(0, metadata.frame_count - 1) : Number.MAX_SAFE_INTEGER;
    const start = current.fall_start_frame;
    const end = current.fall_end_frame ?? maxFrame;
    if (which === "start") {
      const next = clampFrame(start + Math.round(deltaS * fps), 0, end);
      onWindow({ ...current, fall_start_frame: next });
      return;
    }
    const next = clampFrame(end + Math.round(deltaS * fps), start, maxFrame);
    onWindow({ ...current, fall_end_frame: next });
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files.item(0) as (File & { path?: string }) | null;
    const path = file?.path || event.dataTransfer.getData("text/plain");
    if (path) {
      onVideoDrop(path.replace(/^file:\/\/\//i, "").replace(/\//g, "\\"));
    }
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!metadata?.width || !metadata.height) {
      return;
    }
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragStartRef.current = { clientX: event.clientX, clientY: event.clientY };
    setSelection(clientSelection(stageRef.current, event.clientX, event.clientY, event.clientX, event.clientY));
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current;
    if (!start) {
      return;
    }
    setSelection(clientSelection(stageRef.current, start.clientX, start.clientY, event.clientX, event.clientY));
  };

  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current;
    dragStartRef.current = null;
    if (!start || !metadata?.width || !metadata.height) {
      setSelection(null);
      return;
    }
    const picked = imageBoxFromClientRect(start.clientX, start.clientY, event.clientX, event.clientY, stageRef.current, metadata.width, metadata.height);
    if (!picked) {
      setSelection(null);
      return;
    }
    setSelection(picked.css);
    onTarget({
      x_px: picked.box[0] + picked.box[2] / 2,
      y_px: picked.box[1] + picked.box[3] / 2,
      frame: window?.fall_start_frame ?? 0,
      box: picked.box
    });
  };

  return (
    <main className="normal-workbench">
      <section className="normal-hero">
        <div>
          <span className="status-pill success">普通模式</span>
          <h2>单滴平衡-下落测量</h2>
          <p>先标注一颗油滴，再确认 0V 下落窗口。每次分析保存一条 q，随时累积到盲反演。</p>
        </div>
        <button className="ghost-button" onClick={onUseExperimental}>
          <FlaskConical size={16} />
          切到 Experimental
        </button>
      </section>

      <section className="normal-grid">
        <div className="normal-stage glass-panel">
          <div className="panel-heading">
            <span>视频标注</span>
            <small>{target ? `x ${fmtNumber(target.x_px)} / y ${fmtNumber(target.y_px)}` : "点击目标油滴"}</small>
          </div>
          <div
            className="normal-video-shell"
            data-testid="normal-video-shell"
            aria-label="框选目标油滴"
            ref={stageRef}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={() => {
              dragStartRef.current = null;
              setSelection(null);
            }}
          >
            {videoSrc ? (
              <video src={videoSrc} muted className="normal-video" />
            ) : (
              <div className="normal-video-placeholder">
                <motion.span
                  className="normal-video-droplet"
                  animate={{ y: [0, 118, 0], opacity: [0.86, 1, 0.86] }}
                  transition={{ duration: 4.6, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
            )}
            <div className="normal-grid-overlay" aria-hidden="true">
              {Array.from({ length: 5 }, (_, index) => (
                <span key={`h-${index}`} className="normal-grid-line h" style={{ top: `${18 + index * 16}%` }} />
              ))}
              {Array.from({ length: 5 }, (_, index) => (
                <span key={`v-${index}`} className="normal-grid-line v" style={{ left: `${18 + index * 14}%` }} />
              ))}
            </div>
            {target && metadata && (
              <motion.span
                className="target-marker"
                initial={{ scale: 0.72, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                style={{ left: `${(target.x_px / metadata.width) * 100}%`, top: `${(target.y_px / metadata.height) * 100}%` }}
              >
                <Target size={24} />
              </motion.span>
            )}
            {selection && <span className="target-selection" style={selection} />}
            <div className="annotation-hint">
              <MousePointer2 size={15} />
              <span>{target ? "可重新拖拽框选目标油滴" : "拖拽矩形框选目标油滴"}</span>
            </div>
          </div>
        </div>

        <aside className="normal-controls glass-panel">
          <div className="panel-heading">
            <span>输入</span>
            <small>{metadata?.readable ? "视频可读" : "等待检查"}</small>
          </div>
          <div className="normal-form">
            <label>
              <span>视频路径</span>
              <div className="inline-input">
                <input value={videoPath} onChange={(event) => onVideoPath(event.target.value)} placeholder="选择或拖入视频路径" />
                <button className="icon-button" onClick={onOpenVideo} aria-label="打开视频">
                  <FileVideo size={16} />
                </button>
              </div>
            </label>
            <label>
              <span>平衡电压 U</span>
              <input type="number" value={balanceVoltage} onChange={(event) => onBalanceVoltage(Number(event.target.value) || 0)} />
            </label>
            <div className="normal-action-row">
              <button className="ghost-button" onClick={() => onInspect()}>
                <Gauge size={16} />
                检查视频
              </button>
              <button className="ghost-button" onClick={onSuggestWindow} disabled={!videoPath}>
                <Search size={16} />
                建议边界
              </button>
            </div>
          </div>

          <div className="boundary-card">
            <div>
              <strong>下落开始</strong>
              <span>{fmtNumber(startTime)} s</span>
            </div>
            <NudgeControls onNudge={(delta) => setBoundary("start", delta)} />
          </div>
          <div className="boundary-card">
            <div>
              <strong>下落结束</strong>
              <span>{fmtNumber(endTime)} s</span>
            </div>
            <NudgeControls onNudge={(delta) => setBoundary("end", delta)} />
          </div>

          <button className="primary-button full" onClick={onRun} disabled={!videoPath || !target || !window || isRunning}>
            <Play size={17} />
            {isRunning ? "普通模式分析中" : "生成 q 记录"}
          </button>
        </aside>
      </section>

      <section className="normal-bottom-grid">
        <div className="glass-panel q-basket">
          <div className="panel-heading">
            <span>q 记录篮</span>
            <small>可用于盲反演 {usableSelectedCount} / 已选择 {selectedCount}</small>
          </div>
          <div className="usable-count-banner">
            <BadgeCheck size={18} />
            <strong>最终报告前可用 q：{usableSelectedCount}</strong>
            <span>{usableSelectedCount >= 3 ? "已满足双算法反演的最小数量" : "至少需要 3 条有效 q"}</span>
          </div>
          <div className="q-record-list">
            {qRecords.length === 0 ? (
              <div className="empty-q">
                <CircleDot size={18} />
                <span>还没有 q 记录。可以先分析一个视频，之后继续追加。</span>
              </div>
            ) : (
              qRecords.map((record) => (
                <button key={record.record_id} className={`q-record ${record.selected === false ? "off" : ""}`} onClick={() => onToggleRecord(record.record_id)}>
                  {record.selected === false ? <ToggleLeft size={20} /> : <ToggleRight size={20} />}
                  <span>{record.record_id}</span>
                  <strong>{fmtCharge(record.q_C)}</strong>
                  <small>{record.usable_for_inversion ? "usable" : "diagnostic"}</small>
                </button>
              ))
            )}
          </div>
          <div className="panel-actions right">
            <button className="primary-button" onClick={onEstimate} disabled={usableSelectedCount < 3}>
              <Calculator size={17} />
              运行双盲反演
            </button>
          </div>
        </div>

        <div className="glass-panel inversion-card">
          <div className="panel-heading">
            <span>双算法结果</span>
            <small>{elementary ? `${elementary.usable_q_count} q` : "等待 q 记录"}</small>
          </div>
          <div className="algorithm-switch">
            <button className="active">普通算法</button>
            <button>实验性算法</button>
          </div>
          <div className="inversion-grid">
            <ResultMetric label="e" value={fmtCharge(elementary?.normal_algorithm?.e_hat_C)} />
            <ResultMetric label="状态" value={elementary?.normal_algorithm?.status ?? "-"} />
            <ResultMetric label="Experimental" value={elementary?.experimental_algorithm?.status ?? "-"} />
            <ResultMetric label="report" value={elementary?.reportable ? "可写入" : "-"} />
          </div>
          <div className="tracking-legend">
            <LegendDot tone="tracking" label="tracking" />
            <LegendDot tone="missing" label="missing" />
            <LegendDot tone="reacquired" label="reacquired" />
            <LegendDot tone="fit" label="fit interval" />
          </div>
        </div>
      </section>
    </main>
  );
}

function NudgeControls({ onNudge }: { onNudge: (delta: number) => void }) {
  return (
    <div className="nudge-controls">
      {[-1, -0.1, 0.1, 1].map((delta) => (
        <button key={delta} onClick={() => onNudge(delta)}>
          {delta > 0 ? "+" : ""}
          {delta}s
        </button>
      ))}
    </div>
  );
}

function ResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="result-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function LegendDot({ tone, label }: { tone: string; label: string }) {
  return (
    <span className={`legend-dot ${tone}`}>
      <i />
      {label}
    </span>
  );
}

function clampFrame(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function clientSelection(stage: HTMLDivElement | null, x0: number, y0: number, x1: number, y1: number) {
  const rect = stage?.getBoundingClientRect();
  if (!rect) {
    return null;
  }
  const left = Math.max(0, Math.min(x0, x1) - rect.left);
  const top = Math.max(0, Math.min(y0, y1) - rect.top);
  const width = Math.min(rect.width - left, Math.abs(x1 - x0));
  const height = Math.min(rect.height - top, Math.abs(y1 - y0));
  return { left, top, width, height };
}

function imageBoxFromClientRect(x0: number, y0: number, x1: number, y1: number, stage: HTMLDivElement | null, imageWidth: number, imageHeight: number) {
  const rect = stage?.getBoundingClientRect();
  if (!rect) {
    return null;
  }
  const videoAspect = imageWidth / imageHeight;
  const shellAspect = rect.width / rect.height;
  const displayWidth = shellAspect > videoAspect ? rect.height * videoAspect : rect.width;
  const displayHeight = shellAspect > videoAspect ? rect.height : rect.width / videoAspect;
  const offsetX = rect.left + (rect.width - displayWidth) / 2;
  const offsetY = rect.top + (rect.height - displayHeight) / 2;
  const leftClient = Math.max(offsetX, Math.min(x0, x1));
  const rightClient = Math.min(offsetX + displayWidth, Math.max(x0, x1));
  const topClient = Math.max(offsetY, Math.min(y0, y1));
  const bottomClient = Math.min(offsetY + displayHeight, Math.max(y0, y1));
  if (rightClient <= leftClient || bottomClient <= topClient) {
    return null;
  }
  const minDisplaySize = 8;
  const boxLeft = ((leftClient - offsetX) / displayWidth) * imageWidth;
  const boxTop = ((topClient - offsetY) / displayHeight) * imageHeight;
  const boxWidth = Math.max(((rightClient - leftClient) / displayWidth) * imageWidth, (minDisplaySize / displayWidth) * imageWidth);
  const boxHeight = Math.max(((bottomClient - topClient) / displayHeight) * imageHeight, (minDisplaySize / displayHeight) * imageHeight);
  const css = {
    left: leftClient - rect.left,
    top: topClient - rect.top,
    width: Math.max(minDisplaySize, rightClient - leftClient),
    height: Math.max(minDisplaySize, bottomClient - topClient)
  };
  return {
    box: [boxLeft, boxTop, Math.min(imageWidth - boxLeft, boxWidth), Math.min(imageHeight - boxTop, boxHeight)] as [number, number, number, number],
    css
  };
}

function toFileUrl(path: string) {
  if (!path) {
    return "";
  }
  if (/^[a-z]+:\/\//i.test(path)) {
    return path;
  }
  return `file:///${path.replace(/\\/g, "/").replace(/^\/+/, "")}`;
}
