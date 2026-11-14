import { ArrowLeft, Check, FolderOpen, Play, RotateCcw, Save, Scissors, Target, Video } from "lucide-react";
import type {
  NormalBoundary,
  NormalCrossingEvent,
  NormalGrid,
  NormalProgressEvent,
  NormalRecord,
  NormalSession,
  VideoMetadata
} from "../../types";
import type { VideoBox } from "./videoGeometry";
import { fmtCharge, fmtNumber, fmtScientific } from "../../lib/format";
import { clampBoundary, diagnosticLabel, fixedOrDash, parameterLabels, recordStatusLabel } from "./workspaceModel";
import { CrossingFramePlayer } from "./FramePlayers";

export function ProgressBox({ progress, busy }: { progress: NormalProgressEvent | null; busy: boolean }) {
  if (!busy) return null;
  const percent = typeof progress?.fraction === "number" ? Math.round(progress.fraction * 100) : null;
  return (
    <div className="normal-progress-box" role="status">
      <strong>{progress?.label ?? "正在处理…"}</strong>
      <div className="normal-progress-track" role="progressbar" aria-label="处理进度" aria-valuenow={percent ?? undefined} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: percent === null ? "34%" : `${percent}%` }} className={percent === null ? "indeterminate" : ""} />
      </div>
      {percent !== null ? <small>{percent}%{progress?.current != null && progress?.total != null ? ` · ${progress.current} / ${progress.total}${progress.unit === "frames" ? " 帧" : ""}` : ""}</small> : null}
    </div>
  );
}

export function ImportPanel(props: {
  videoPath: string;
  metadata: VideoMetadata | null;
  busy: boolean;
  onPath: (path: string) => void;
  onInspect: () => void;
  onOpen: () => void;
  onStart: () => void;
}) {
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <strong>导入视频</strong>
      </div>
      <div className="normal-path-row">
        <input value={props.videoPath} onChange={(event) => props.onPath(event.target.value)} placeholder="拖入视频或粘贴绝对路径" />
        <button className="ghost-button" onClick={props.onOpen}>
          <FolderOpen size={16} />
          选择
        </button>
      </div>
      <div className="normal-meta-grid">
        <InfoTile label="帧率" value={fixedOrDash(props.metadata?.fps)} />
        <InfoTile label="帧数" value={fixedOrDash(props.metadata?.frame_count, 0)} />
        <InfoTile label="分辨率" value={props.metadata ? `${props.metadata.width} x ${props.metadata.height}` : "-"} />
        <InfoTile label="时长" value={`${fixedOrDash(props.metadata?.duration_s)} s`} />
      </div>
      <button className="ghost-button full" disabled={props.busy || !props.videoPath} onClick={props.onInspect}>
        <Video size={16} />
        载入视频
      </button>
      <button className="primary-button full" disabled={props.busy || !props.metadata?.readable} onClick={props.onStart}>
        <Play size={16} />
        开始处理
      </button>
    </div>
  );
}

export function BoundaryPanel(props: {
  boundary: NormalBoundary;
  metadata: VideoMetadata | null;
  grid: NormalGrid | null;
  busy: boolean;
  onBoundary: (boundary: NormalBoundary) => void;
  onAdjust: (field: "zero_v_start_s" | "zero_v_end_s", delta: number) => void;
  onJump: (time: number) => void;
  onConfirm: () => void;
}) {
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <strong>确认零电压区间</strong>
      </div>
      {(["zero_v_start_s", "zero_v_end_s"] as const).map((field) => (
        <div className="normal-boundary-editor" key={field}>
          <div className="normal-boundary-heading">
            <label>{field === "zero_v_start_s" ? "开始时间（秒）" : "结束时间（秒）"}</label>
            <button className="normal-seek-button" onClick={() => props.onJump(props.boundary[field])}>定位画面</button>
          </div>
          <div className="normal-step-row">
            <button onClick={() => props.onAdjust(field, -1)}>-1s</button>
            <button onClick={() => props.onAdjust(field, -0.1)}>-0.1s</button>
            <input
              type="number"
              step="0.1"
              value={props.boundary[field]}
              onChange={(event) => props.onBoundary(clampBoundary({ ...props.boundary, [field]: Number(event.target.value) }, props.metadata))}
            />
            <button onClick={() => props.onAdjust(field, 0.1)}>+0.1s</button>
            <button onClick={() => props.onAdjust(field, 1)}>+1s</button>
          </div>
        </div>
      ))}
      {(props.boundary.flags ?? []).map((flag) => <div className="normal-drop-hint" key={flag}>{diagnosticLabel(flag)}</div>)}
      <div className="normal-diagnostic-box">
        <strong>{props.grid?.valid ? "网格已识别" : "网格识别失败"}</strong>
        {props.grid?.valid ? <span>像素标尺：{fmtScientific(props.grid.scale_y_m_per_px, 2)} m/px</span> : <span>请检查视频是否清晰、网格是否完整。</span>}
      </div>
      <button className="primary-button full" disabled={props.busy || !props.grid?.valid} onClick={props.onConfirm}>
        <Check size={16} />
        确认边界
      </button>
    </div>
  );
}

export function TargetPanel(props: {
  selectionTime: number;
  selectionWindow: { start_s: number; end_s: number; source?: string };
  selectionBox: VideoBox | null;
  balanceVoltage: string;
  balanceConfirmed: boolean;
  advancedOpen: boolean;
  parameterKeys: string[];
  parameterFieldValue: (key: string) => string;
  overrides: Record<string, string>;
  busy: boolean;
  onSelectionTime: (time: number) => void;
  onAdjustSelection: (delta: number) => void;
  onVoltage: (value: string) => void;
  onBalanceConfirmed: (value: boolean) => void;
  onAdvancedOpen: (value: boolean) => void;
  onOverride: (key: string, value: string) => void;
  onTrack: () => void;
  onBackBoundary: () => void;
}) {
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <strong>框选油滴</strong>
      </div>
      <button className="ghost-button full" disabled={props.busy} onClick={props.onBackBoundary}>
        <ArrowLeft size={16} />
        修改零电压区间
      </button>
      <div className="normal-boundary-editor">
        <label>框选时刻（秒）</label>
        <small>允许范围：{fixedOrDash(props.selectionWindow.start_s, 2)} - {fixedOrDash(props.selectionWindow.end_s, 2)} s</small>
        <div className="normal-step-row compact">
          <button onClick={() => props.onAdjustSelection(-1)}>-1s</button>
          <button onClick={() => props.onAdjustSelection(-0.1)}>-0.1s</button>
          <input
            type="number"
            step="0.1"
            min={props.selectionWindow.start_s}
            max={props.selectionWindow.end_s}
            value={props.selectionTime}
            onChange={(event) => {
              const raw = Number(event.target.value);
              const value = Math.max(props.selectionWindow.start_s, Math.min(props.selectionWindow.end_s, raw));
              props.onSelectionTime(value);
            }}
          />
          <button onClick={() => props.onAdjustSelection(0.1)}>+0.1s</button>
          <button onClick={() => props.onAdjustSelection(1)}>+1s</button>
        </div>
      </div>
      <div className="normal-diagnostic-box">
        <strong>矩形框选</strong>
        <span>{props.selectionBox ? "已框选，可拖动重新选择" : "在视频画面上拖拽一个矩形包住油滴"}</span>
      </div>
      <label className="normal-field">
        <span>平衡电压 V</span>
        <input value={props.balanceVoltage} onChange={(event) => props.onVoltage(event.target.value)} placeholder="例如 239" inputMode="decimal" />
      </label>
      <label className="normal-checkline">
        <input type="checkbox" checked={props.balanceConfirmed} onChange={(event) => props.onBalanceConfirmed(event.target.checked)} />
        <span>我确认该油滴在此电压下近似静止</span>
      </label>
      <button className="ghost-button full" onClick={() => props.onAdvancedOpen(!props.advancedOpen)}>
        <RotateCcw size={16} />
        实验参数
      </button>
      {props.advancedOpen ? (
        <div className="normal-param-grid">
          {props.parameterKeys.map((key) => (
            <label key={key}>
              <span>{parameterLabels[key]}</span>
              <input value={props.parameterFieldValue(key)} onChange={(event) => props.onOverride(key, event.target.value)} />
              {props.overrides[key] !== undefined ? <small>已修改</small> : null}
            </label>
          ))}
        </div>
      ) : null}
      <button className="primary-button full" disabled={props.busy || !props.selectionBox || !props.balanceConfirmed || !props.balanceVoltage} onClick={props.onTrack}>
        <Target size={16} />
        确认框选并开始追踪
      </button>
    </div>
  );
}

export function ReviewPanel(props: {
  record: NormalRecord | null;
  currentCrossing: NormalCrossingEvent | null;
  busy: boolean;
  onPrepareReview: (event: NormalCrossingEvent) => void;
  onReview: (result: "same_drop" | "different_drop") => void;
  onContinue: () => void;
  onBackTarget: () => void;
  onBackBoundary: () => void;
}) {
  const crossings = props.record?.crossings ?? [];
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <strong>复核轨迹</strong>
      </div>
      <div className="normal-diagnostic-box">
        <strong>{recordStatusLabel(props.record?.status)}</strong>
        <span>待检查 {crossings.filter((event) => !event.review_result).length} 个过线片段</span>
      </div>
      <div className="normal-crossing-list">
        {crossings.map((event, index) => (
          <button key={event.event_id} className={props.currentCrossing?.event_id === event.event_id ? "active" : ""} onClick={() => props.onPrepareReview(event)}>
            <Scissors size={14} />
            <span>过线片段 {index + 1}</span>
            <small>{fixedOrDash(event.start_time_s ?? event.time_s, 2)}s · {event.review_result === "same_drop" ? "同一颗油滴" : event.review_result === "different_drop" ? "油滴不一致" : "待复核"}</small>
          </button>
        ))}
        {crossings.length === 0 ? <span className="normal-drop-hint">没有需要复核的过线片段。</span> : null}
      </div>
      {props.currentCrossing ? (
        <div className="normal-review-clip">
          <CrossingFramePlayer event={props.currentCrossing} />
          <div className="panel-actions">
            <button className="primary-button small" disabled={props.busy} onClick={() => props.onReview("same_drop")}>
              同一颗油滴
            </button>
            <button className="ghost-button" disabled={props.busy} onClick={() => props.onReview("different_drop")}>
              不是同一颗
            </button>
          </div>
        </div>
      ) : null}
      <div className="panel-actions normal-review-navigation">
        <button className="ghost-button" disabled={props.busy} onClick={props.onBackTarget}>
          返回框选
        </button>
        <button className="ghost-button" disabled={props.busy} onClick={props.onBackBoundary}>
          修改 0V
        </button>
      </div>
      {props.record?.status === "pending_user_confirmation" ? (
        <button className="ghost-button full" onClick={props.onContinue}>查看测量结果</button>
      ) : null}
    </div>
  );
}

export function ResultsPanel(props: {
  session: NormalSession | null;
  selectedRecord: NormalRecord | null;
  isRecordAcceptable: boolean;
  busy: boolean;
  onSelectRecord: (id: string) => void;
  onAccept: () => void;
  onReject: () => void;
  onBackReview: () => void;
  onBackBoundary: () => void;
  onNextDrop: () => void;
}) {
  const record = props.selectedRecord;
  const fit = (record?.fit as Record<string, any> | undefined) ?? {};

  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <strong>测量结果</strong>
      </div>
      {record ? (
        <>
          <div className="normal-result-hero">
            <span>{recordStatusLabel(record.status)}</span>
            <strong>{fmtCharge(record.q_C)}</strong>
            <small>σq = {fmtCharge(record.sigma_q_C)}</small>
          </div>
          <div className="normal-meta-grid">
            <InfoTile label="半径" value={`${fmtNumber(Number(record.radius_m) * 1e6, 4)} μm`} />
            <InfoTile label="下落速度" value={`${fmtScientific(record.fall_velocity_m_s, 4)} m/s`} />
            <InfoTile label="R²" value={fixedOrDash(fit.r2 as number | undefined, 3)} />
            <InfoTile label="拟合点" value={String(fit.fit_point_count ?? "-")} />
          </div>
          <p className="normal-result-note">σq 由速度拟合误差传播，未计仪器与物性参数误差。</p>
          <div className="panel-actions normal-result-actions">
            {record.status === "accepted" && record.kept ? (
              <button className="primary-button" disabled={props.busy} onClick={props.onNextDrop}>下一颗油滴</button>
            ) : (
              <button className="primary-button" disabled={props.busy || !props.isRecordAcceptable} onClick={props.onAccept}><Save size={15} />确认保留</button>
            )}
            <button className="ghost-button" disabled={props.busy} onClick={props.onBackReview}>返回复核</button>
            <button className="ghost-button" disabled={props.busy} onClick={props.onBackBoundary}>修改 0V</button>
            <button className="ghost-button" disabled={props.busy} onClick={props.onReject}>排除并调整</button>
          </div>
        </>
      ) : (
        <div className="normal-drop-hint">还没有本次测量记录。</div>
      )}
      <details className="normal-record-history">
        <summary>测量记录（{props.session?.records.length ?? 0} 条）</summary>
        <div className="normal-record-list">
          {(props.session?.records ?? []).map((item, index) => (
            <button key={item.record_id} className={item.record_id === record?.record_id ? "active" : ""} onClick={() => props.onSelectRecord(item.record_id)}>
              <span className="record-id">测量 {index + 1}</span>
              <strong>{fmtCharge(item.q_C)}</strong>
              <small>{recordStatusLabel(item.status)}</small>
            </button>
          ))}
        </div>
      </details>
    </div>
  );
}

export function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="normal-info-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
