import { useMemo, useRef, useState } from "react";
import type { DragEvent, MouseEvent } from "react";
import { ArrowLeft, Check, Download, FolderOpen, Play, RotateCcw, Save, Target, Video } from "lucide-react";
import type {
  NormalBoundary,
  NormalGrid,
  NormalInversionResult,
  NormalPrepareVideoResponse,
  NormalRecord,
  NormalSession,
  VideoMetadata
} from "../../types";
import { desktopApi } from "../../lib/desktopApi";

type NormalWorkspaceProps = {
  onBack: () => void;
};

type TargetPick = {
  x: number;
  y: number;
  frame: number;
  time_s: number;
};

type AdvancedParams = {
  plate_distance_m: number;
  measurement_distance_m: number;
  air_viscosity_Pa_s: number;
  pressure_Pa: number;
  oil_density_kg_m3: number;
  cunningham_b_Pa_m: number;
};

const defaultAdvanced: AdvancedParams = {
  plate_distance_m: 0.005,
  measurement_distance_m: 0.001,
  air_viscosity_Pa_s: 1.81e-5,
  pressure_Pa: 101325,
  oil_density_kg_m3: 886,
  cunningham_b_Pa_m: 8.2e-3
};

const formatSci = (value?: number | null, digits = 3) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return value.toExponential(digits);
};

const formatFixed = (value?: number | null, digits = 2) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(digits);
};

function clampBoundary(boundary: NormalBoundary, metadata: VideoMetadata | null): NormalBoundary {
  const duration = metadata?.duration_s && Number.isFinite(metadata.duration_s) ? metadata.duration_s : Number.POSITIVE_INFINITY;
  const start = Math.max(0, Math.min(boundary.zero_v_start_s, duration));
  const end = Math.max(start, Math.min(boundary.zero_v_end_s, duration));
  return { ...boundary, zero_v_start_s: start, zero_v_end_s: end, source: "manual_ui" };
}

export function NormalWorkspace({ onBack }: NormalWorkspaceProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [session, setSession] = useState<NormalSession | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [boundary, setBoundary] = useState<NormalBoundary>({ zero_v_start_s: 0, zero_v_end_s: 1, source: "manual_ui" });
  const [grid, setGrid] = useState<NormalGrid | null>(null);
  const [target, setTarget] = useState<TargetPick | null>(null);
  const [balanceVoltage, setBalanceVoltage] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advanced, setAdvanced] = useState<AdvancedParams>(defaultAdvanced);
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [inversion, setInversion] = useState<NormalInversionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Normal 模式：导入视频，确认 0V 下落段，点选一颗油滴。");

  const keptValidCount = session?.counts?.kept_valid ?? session?.counts?.selected_valid ?? 0;
  const effectiveTopPx = Number(grid?.effective_top_px ?? grid?.second_line_y ?? Number.NaN);
  const effectiveBottomPx = Number(grid?.effective_bottom_px ?? grid?.penultimate_line_y ?? Number.NaN);
  const gridLineCount = (grid?.line_y_px as unknown[] | undefined)?.length ?? (grid?.grid_lines_y as unknown[] | undefined)?.length ?? 0;
  const selectedRecord = useMemo(
    () => session?.records.find((record) => record.record_id === selectedRecordId) ?? session?.records[session.records.length - 1] ?? null,
    [selectedRecordId, session?.records]
  );

  const prepareVideo = async (path: string) => {
    if (!path) {
      setMessage("请输入或选择视频路径。");
      return;
    }
    setBusy(true);
    try {
      const result: NormalPrepareVideoResponse = await desktopApi.normalPrepareVideo({
        video_path: path,
        session_root: session?.session_root,
        config_overrides: {
          physics: advanced,
          grid: { measurement_distance_m: advanced.measurement_distance_m }
        }
      });
      setSession(result.session);
      setMetadata(result.metadata);
      setVideoPath(result.video_path || path);
      setVideoUrl(result.video_url || "");
      setBoundary(clampBoundary(result.boundary, result.metadata));
      setGrid(result.grid);
      setTarget(null);
      setMessage("视频导入完成。请用秒级按钮确认 0V 下落段，再在画面中点选油滴。");
    } catch (error) {
      setMessage(`视频导入失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const openVideo = async () => {
    const path = await desktopApi.openVideoDialog();
    if (path) {
      await prepareVideo(path);
    }
  };

  const onDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0] as (File & { path?: string }) | undefined;
    const path = file?.path || videoPath;
    if (path) {
      await prepareVideo(path);
    }
  };

  const adjustBoundary = (field: "zero_v_start_s" | "zero_v_end_s", delta: number) => {
    setBoundary((current) => clampBoundary({ ...current, [field]: Number((current[field] + delta).toFixed(3)) }, metadata));
  };

  const updateAdvanced = (key: keyof AdvancedParams, value: string) => {
    setAdvanced((current) => ({ ...current, [key]: Number(value) }));
  };

  const pickTarget = (event: MouseEvent<HTMLVideoElement>) => {
    const video = videoRef.current;
    if (!video || !metadata) {
      return;
    }
    const rect = video.getBoundingClientRect();
    const sourceWidth = video.videoWidth || metadata.width || rect.width;
    const sourceHeight = video.videoHeight || metadata.height || rect.height;
    const x = ((event.clientX - rect.left) / rect.width) * sourceWidth;
    const y = ((event.clientY - rect.top) / rect.height) * sourceHeight;
    const time_s = video.currentTime || boundary.zero_v_start_s;
    setTarget({
      x,
      y,
      time_s,
      frame: Math.max(0, Math.round(time_s * (metadata.fps || 1)))
    });
    setMessage("已选中目标油滴。运行测量前请确认平衡电压。");
  };

  const runMeasurement = async () => {
    if (!metadata || !target || !grid) {
      setMessage("需要先导入视频、完成网格识别并点选油滴。");
      return;
    }
    const voltage = Number(balanceVoltage);
    if (!Number.isFinite(voltage) || voltage <= 0) {
      setMessage("平衡电压必填，且必须为正数。");
      return;
    }
    setBusy(true);
    try {
      const response = await desktopApi.normalSaveMeasurement({
        session_root: session?.session_root,
        video_path: videoPath,
        boundary,
        grid,
        balance_voltage_V: voltage,
        target: {
          target_frame: target.frame,
          target_time_s: target.time_s,
          source_center: { x: target.x, y: target.y },
          source_video_box: { x: Math.max(0, target.x - 14), y: Math.max(0, target.y - 14), width: 28, height: 28 }
        },
        parameter_overrides: {
          physics: advanced,
          grid: { measurement_distance_m: advanced.measurement_distance_m }
        }
      });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setInversion(response.session.inversion ?? null);
      setMessage(response.record.valid ? "本滴 q 记录已保存，可继续换视频或换油滴。" : `记录已保存，但未通过 q 校验：${(response.record.flags || []).join(", ")}`);
    } catch (error) {
      setMessage(`测量失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const toggleRecord = async (record: NormalRecord) => {
    setBusy(true);
    try {
      const nextSession = await desktopApi.normalSelectRecord({
        session_root: session?.session_root,
        record_id: record.record_id,
        kept: !record.kept
      });
      setSession(nextSession);
      setMessage(!record.kept ? "记录已保留用于盲反演。" : "记录已从盲反演输入中排除。");
    } catch (error) {
      setMessage(`更新记录失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const runInversion = async () => {
    setBusy(true);
    try {
      const response = await desktopApi.normalRunInversion({ session_root: session?.session_root });
      setSession(response.session);
      setInversion(response.inversion);
      setMessage(response.inversion.status === "ok" ? "盲反演完成。" : `盲反演未完成：${(response.inversion.flags || []).join(", ") || response.inversion.status}`);
    } catch (error) {
      setMessage(`盲反演失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const exportSession = async () => {
    try {
      const result = await desktopApi.normalExportSession({ session_root: session?.session_root });
      setMessage(JSON.stringify(result).includes("canceled") ? "已取消导出。" : "Normal session 已导出。");
    } catch (error) {
      setMessage(`导出失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const reviewCrossing = (event: { review_start_time_s?: number; event_id?: string }) => {
    if (videoRef.current && typeof event.review_start_time_s === "number") {
      videoRef.current.currentTime = event.review_start_time_s;
      void videoRef.current.play();
    }
    setMessage(`正在复核 crossing event：${event.event_id ?? "unknown"}`);
  };

  return (
    <div className="desktop-frame normal-workspace">
      <header className="normal-topbar">
        <button className="icon-button" onClick={onBack} aria-label="返回模式选择">
          <ArrowLeft size={17} />
        </button>
        <div className="topbar__brand">
          <strong>Normal</strong>
          <span>平衡电压 + 0V 下落逐滴测量</span>
        </div>
        <div className="normal-topbar__actions">
          <button className="ghost-button" onClick={openVideo}>
            <FolderOpen size={16} />
            选择视频
          </button>
          <button className="ghost-button" disabled={!session?.session_root} onClick={exportSession}>
            <Download size={16} />
            导出 session
          </button>
          <button className="primary-button small" disabled={busy || keptValidCount < 3} onClick={runInversion}>
            <Play size={16} />
            盲反演
          </button>
        </div>
      </header>

      <main className="normal-grid">
        <section className="panel normal-import" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
          <div className="section-heading">
            <span>视频导入</span>
            <strong>0V 段与元数据</strong>
          </div>
          <div className="normal-path-row">
            <input value={videoPath} onChange={(event) => setVideoPath(event.target.value)} placeholder="拖入视频或粘贴绝对路径" />
            <button className="primary-button small" disabled={busy} onClick={() => prepareVideo(videoPath)}>
              <Video size={16} />
              导入
            </button>
          </div>
          {metadata ? (
            <div className="normal-meta">
              <span>{metadata.fps.toFixed(2)} fps</span>
              <span>{metadata.frame_count} frames</span>
              <span>{metadata.width} × {metadata.height}</span>
              <span>{metadata.duration_s.toFixed(2)} s</span>
            </div>
          ) : (
            <div className="normal-drop-hint">拖入视频后会显示 fps、帧数、分辨率和时长。</div>
          )}
          <div className="normal-video-wrap">
            {videoUrl ? (
              <video ref={videoRef} src={videoUrl} controls onClick={pickTarget} />
            ) : (
              <div className="normal-video-placeholder">视频预览</div>
            )}
            {target ? (
              <div className="target-readout">
                <Target size={14} />
                x={target.x.toFixed(1)}, y={target.y.toFixed(1)}, t={target.time_s.toFixed(2)}s
              </div>
            ) : null}
          </div>
        </section>

        <section className="panel normal-controls">
          <div className="section-heading">
            <span>测量设置</span>
            <strong>秒级 0V 边界</strong>
          </div>
          <div className="boundary-editor">
            {(["zero_v_start_s", "zero_v_end_s"] as const).map((field) => (
              <div className="boundary-row" key={field}>
                <label>{field === "zero_v_start_s" ? "0V start" : "0V end"}</label>
                <div className="stepper">
                  <button onClick={() => adjustBoundary(field, -1)}>-1s</button>
                  <button onClick={() => adjustBoundary(field, -0.1)}>-0.1s</button>
                  <input
                    type="number"
                    step="0.1"
                    value={boundary[field]}
                    onChange={(event) => setBoundary((current) => clampBoundary({ ...current, [field]: Number(event.target.value), source: "manual_ui" }, metadata))}
                  />
                  <button onClick={() => adjustBoundary(field, 0.1)}>+0.1s</button>
                  <button onClick={() => adjustBoundary(field, 1)}>+1s</button>
                </div>
              </div>
            ))}
          </div>
          <label className="normal-field">
            <span>平衡电压 V</span>
            <input value={balanceVoltage} onChange={(event) => setBalanceVoltage(event.target.value)} placeholder="例如 239" inputMode="decimal" />
          </label>
          <button className="ghost-button full" onClick={() => setAdvancedOpen((current) => !current)}>
            <RotateCcw size={16} />
            本次测量高级物理参数
          </button>
          {advancedOpen ? (
            <div className="advanced-grid">
              {Object.entries(advanced).map(([key, value]) => (
                <label key={key}>
                  <span>{key}</span>
                  <input value={value} onChange={(event) => updateAdvanced(key as keyof AdvancedParams, event.target.value)} />
                </label>
              ))}
            </div>
          ) : null}
          <div className="grid-summary">
            <strong>网格识别</strong>
            <span>有效区域：{formatFixed(effectiveTopPx, 0)} px 到 {formatFixed(effectiveBottomPx, 0)} px</span>
            <span>横向线：{gridLineCount}</span>
            <span>scale_y：{formatSci(grid?.scale_y_m_per_px, 2)} m/px</span>
          </div>
          <button className="primary-button full" disabled={busy || !target || !balanceVoltage} onClick={runMeasurement}>
            <Save size={16} />
            保存本滴 q 记录
          </button>
        </section>

        <section className="panel normal-records">
          <div className="section-heading">
            <span>Session</span>
            <strong>{keptValidCount}/3 有效 q</strong>
          </div>
          <div className="records-table">
            {(session?.records ?? []).map((record) => (
              <button key={record.record_id} className={record.record_id === selectedRecord?.record_id ? "record-row active" : "record-row"} onClick={() => setSelectedRecordId(record.record_id)}>
                <span>{record.record_id}</span>
                <span>{record.valid ? <Check size={14} /> : "!"}</span>
                <span>{formatSci(record.q_C)}</span>
                <span>± {formatSci(record.sigma_q_C)}</span>
                <span>{record.kept ? "保留" : "排除"}</span>
              </button>
            ))}
            {session?.records?.length ? null : <div className="normal-drop-hint">保存至少 3 条有效 q 后运行盲反演。</div>}
          </div>
          {selectedRecord ? (
            <div className="record-detail">
              <div>
                <strong>{formatSci(selectedRecord.q_C)} C</strong>
                <span>sigma {formatSci(selectedRecord.sigma_q_C)} C</span>
              </div>
              <button className="ghost-button" onClick={() => toggleRecord(selectedRecord)}>
                {selectedRecord.kept ? "排除本条" : "保留本条"}
              </button>
              <div className="crossing-list">
                <strong>Crossing review</strong>
                {(selectedRecord.crossings || []).slice(0, 8).map((event) => (
                  <button key={event.event_id} onClick={() => reviewCrossing(event)}>
                    {event.event_id} · {formatFixed(event.time_s, 2)}s
                  </button>
                ))}
                {selectedRecord.crossings?.length ? null : <span>暂无 crossing event。</span>}
              </div>
            </div>
          ) : null}
        </section>

        <section className="panel normal-inversion">
          <div className="section-heading">
            <span>AI 复核</span>
            <strong>盲反演与模型对比</strong>
          </div>
          {inversion ? (
            <div className="inversion-summary">
              <span>status: {inversion.status ?? "unknown"}</span>
              <strong>e = {formatSci(inversion.e_hat_C)} C</strong>
              <span>sigma_e = {formatSci(inversion.sigma_e_C)} C</span>
              <span>valid q = {inversion.valid_q_count ?? keptValidCount}</span>
              <span>quantized: {String(inversion.comparison?.quantized_favored ?? inversion.quantized?.favored ?? "unknown")}</span>
            </div>
          ) : (
            <div className="normal-drop-hint">Normal 使用带不确定度权重的整数倍残差网格搜索；连续模型只作为对照。</div>
          )}
        </section>
      </main>

      <div className="status-toast" role="status">
        {busy ? "正在处理..." : message}
      </div>
    </div>
  );
}
