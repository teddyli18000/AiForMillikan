import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, MouseEvent, RefObject } from "react";
import { ArrowLeft, Check, ChevronsLeft, ChevronsRight, Download, FileVideo, FolderOpen, Pause, Play, RotateCcw, Save, Scissors, StepBack, StepForward, Target, Video } from "lucide-react";
import type {
  NormalBoundary,
  NormalCrossingEvent,
  NormalGrid,
  NormalInversionResult,
  NormalProgressEvent,
  NormalRecord,
  NormalSession,
  VideoMetadata
} from "../../types";
import { desktopApi } from "../../lib/desktopApi";

type NormalWorkspaceProps = {
  onBack: () => void;
};

type StageId = "import" | "boundary" | "target" | "review" | "results";

type VideoBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type VideoPoint = {
  x: number;
  y: number;
};

const stages: Array<{ id: StageId; title: string; detail: string }> = [
  { id: "import", title: "导入与预览", detail: "inspect 只读元数据" },
  { id: "boundary", title: "0V 边界确认", detail: "秒级微调起止" },
  { id: "target", title: "框选目标油滴", detail: "平衡确认后追踪" },
  { id: "review", title: "轨迹与 crossing", detail: "人工复核身份" },
  { id: "results", title: "结果与 session", detail: "确认保留再反演" }
];

const physicsKeys = [
  "plate_distance_m",
  "air_viscosity_Pa_s",
  "pressure_Pa",
  "oil_density_kg_m3",
  "cunningham_b_Pa_m"
];

const gridKeys = ["measurement_distance_m"];

const formatSci = (value?: number | null, digits = 3) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return value.toExponential(digits);
};

const formatFixed = (value?: number | null, digits = 2) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(digits);
};

const statusLabel = (status?: string) => {
  const labels: Record<string, string> = {
    pending_crossing_review: "待 crossing 复核",
    pending_user_confirmation: "待用户确认",
    accepted: "已保留",
    diagnostic: "诊断",
    rejected_crossing_identity: "crossing 否决",
    rejected_by_user: "用户排除"
  };
  return labels[status || ""] || status || "未开始";
};

function clampBoundary(boundary: NormalBoundary, metadata: VideoMetadata | null): NormalBoundary {
  const duration = metadata?.duration_s && Number.isFinite(metadata.duration_s) ? metadata.duration_s : Number.POSITIVE_INFINITY;
  const start = Math.max(0, Math.min(Number(boundary.zero_v_start_s || 0), duration));
  const end = Math.max(start, Math.min(Number(boundary.zero_v_end_s || 0), duration));
  return { ...boundary, zero_v_start_s: Number(start.toFixed(3)), zero_v_end_s: Number(end.toFixed(3)), source: "manual_ui" };
}

export function NormalWorkspace({ onBack }: NormalWorkspaceProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const reviewVideoRef = useRef<HTMLVideoElement | null>(null);
  const [stage, setStage] = useState<StageId>("import");
  const [session, setSession] = useState<NormalSession | null>(null);
  const [backendConfig, setBackendConfig] = useState<Record<string, any> | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [boundary, setBoundary] = useState<NormalBoundary>({ zero_v_start_s: 0, zero_v_end_s: 1, source: "manual_ui" });
  const [boundaryDiagnostics, setBoundaryDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [grid, setGrid] = useState<NormalGrid | null>(null);
  const [selectionTime, setSelectionTime] = useState(0);
  const [selectionBox, setSelectionBox] = useState<VideoBox | null>(null);
  const [dragStart, setDragStart] = useState<VideoPoint | null>(null);
  const [balanceVoltage, setBalanceVoltage] = useState("");
  const [balanceConfirmed, setBalanceConfirmed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [parameterOverrides, setParameterOverrides] = useState<Record<string, string>>({});
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [reviewEvent, setReviewEvent] = useState<NormalCrossingEvent | null>(null);
  const [inversion, setInversion] = useState<NormalInversionResult | null>(null);
  const [progress, setProgress] = useState<NormalProgressEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Normal：先导入视频，预览无误后再开始处理。");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    let alive = true;
    desktopApi
      .normalInitialize({})
      .then((result) => {
        if (!alive) return;
        setSession(result.session);
        setBackendConfig(result.config);
      })
      .catch((error) => setMessage(`Normal 初始化失败：${error instanceof Error ? error.message : String(error)}`));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => desktopApi.onNormalProgress((event) => setProgress(event)), []);

  const selectedRecord = useMemo(
    () => session?.records.find((record) => record.record_id === selectedRecordId) ?? session?.records[session.records.length - 1] ?? null,
    [selectedRecordId, session?.records]
  );
  const crossings = selectedRecord?.crossings ?? [];
  const allCrossingsReviewedSame = crossings.every((event) => event.review_result === "same_drop");
  const keptValidCount = session?.counts?.kept_valid ?? 0;
  const gridLineCount = (grid?.grid_lines_y as unknown[] | undefined)?.length ?? (grid?.line_y_px as unknown[] | undefined)?.length ?? 0;
  const effectiveTopPx = Number(grid?.effective_top_px ?? grid?.second_line_y ?? Number.NaN);
  const effectiveBottomPx = Number(grid?.effective_bottom_px ?? grid?.penultimate_line_y ?? Number.NaN);

  const inspectVideo = async (path: string) => {
    if (!path) {
      setMessage("请先选择或拖入视频。");
      return;
    }
    setBusy(true);
    try {
      const result = await desktopApi.normalInspectVideo({ video_path: path });
      setMetadata(result.metadata);
      setVideoPath(result.video_path || path);
      setVideoUrl(result.video_url);
      setDuration(result.metadata.duration_s || 0);
      setBoundary({ zero_v_start_s: 0, zero_v_end_s: Math.min(1, result.metadata.duration_s || 1), source: "manual_ui" });
      setGrid(null);
      setSelectionBox(null);
      setReviewEvent(null);
      setStage("import");
      setMessage("视频预览已就绪。点击开始处理后才会检测 0V 和网格。");
    } catch (error) {
      setMessage(`视频预览失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const openVideo = async () => {
    const path = await desktopApi.openVideoDialog();
    if (path) {
      await inspectVideo(path);
    }
  };

  const onDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files.item(0);
    if (!file) {
      return;
    }
    const path = (await desktopApi.getDroppedFilePath(file)) || "";
    if (path) {
      await inspectVideo(path);
    } else {
      setMessage("无法读取拖入文件路径，请使用文件选择按钮。");
    }
  };

  const startPrepare = async () => {
    if (!videoPath) {
      setMessage("请先导入视频。");
      return;
    }
    setBusy(true);
    setProgress(null);
    try {
      const result = await desktopApi.normalPrepareVideo({ video_path: videoPath, session_root: session?.session_root });
      setSession(result.session);
      setBackendConfig(result.config);
      setMetadata(result.metadata);
      setVideoUrl(result.video_url || videoUrl);
      setBoundary(clampBoundary(result.boundary, result.metadata));
      setBoundaryDiagnostics(result.boundary_diagnostics ?? null);
      setSelectionTime(Number(result.boundary.selection_time_s ?? result.boundary.zero_v_start_s ?? 0));
      setGrid(result.grid);
      setStage("boundary");
      setProgress(null);
      setMessage("已生成 0V 起止建议。请结合视频预览确认边界。");
    } catch (error) {
      setMessage(`开始处理失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const confirmBoundary = async () => {
    setBusy(true);
    try {
      const result = await desktopApi.normalConfirmBoundary({ session_root: session?.session_root, boundary });
      setSession(result.session);
      setSelectionTime(Math.max(0, Number(boundary.selection_time_s ?? boundary.zero_v_start_s ?? 0)));
      jumpTo(Number(boundary.selection_time_s ?? boundary.zero_v_start_s ?? 0));
      setStage("target");
      setMessage("0V 边界已确认。请在 0V 起点附近框选目标油滴。");
    } catch (error) {
      setMessage(`确认边界失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const selectTargetAndTrack = async () => {
    if (!selectionBox || !metadata) {
      setMessage("需要先拖拽矩形框选目标油滴。");
      return;
    }
    const voltage = Number(balanceVoltage);
    if (!Number.isFinite(voltage) || voltage <= 0 || !balanceConfirmed) {
      setMessage("请填写正的平衡电压，并明确确认该油滴在该电压下处于平衡状态。");
      return;
    }
    const targetFrame = Math.max(0, Math.min(metadata.frame_count - 1, Math.round(selectionTime * (metadata.fps || 1))));
    const target = {
      target_frame: targetFrame,
      target_time_s: targetFrame / (metadata.fps || 1),
      source_center: { x: selectionBox.x + selectionBox.width / 2, y: selectionBox.y + selectionBox.height / 2 },
      source_video_box: selectionBox
    };
    setBusy(true);
    setProgress(null);
    try {
      await desktopApi.normalSelectTarget({
        session_root: session?.session_root,
        target,
        balance_voltage_V: voltage,
        balance_confirmed: true,
        parameter_overrides: buildParameterOverrides()
      });
      const response = await desktopApi.normalSaveMeasurement({ session_root: session?.session_root });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setStage(response.record.status === "pending_crossing_review" ? "review" : "results");
      setProgress(null);
      setMessage(response.record.status === "pending_crossing_review" ? "追踪完成。请逐一复核 crossing 身份。" : "追踪和 q 计算完成。请确认是否保留。");
    } catch (error) {
      setMessage(`追踪失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const prepareCrossingReview = async (event: NormalCrossingEvent) => {
    if (!selectedRecord) return;
    setBusy(true);
    try {
      const response = await desktopApi.normalPrepareCrossingReview({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        event_id: event.event_id
      });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setReviewEvent(response.event ?? event);
      setMessage("局部放大复核片段已生成。");
      window.setTimeout(() => {
        reviewVideoRef.current?.play().catch(() => undefined);
      }, 80);
    } catch (error) {
      setMessage(`生成 crossing 复核失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const submitCrossingReview = async (result: "same_drop" | "different_drop") => {
    if (!selectedRecord || !reviewEvent) return;
    setBusy(true);
    try {
      const response = await desktopApi.normalReviewCrossing({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        event_id: reviewEvent.event_id,
        result
      });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setReviewEvent(response.record.crossings?.find((event) => event.event_id === reviewEvent.event_id) ?? null);
      if (response.record.status === "pending_user_confirmation") {
        setStage("results");
        setMessage("所有 crossing 已确认同一颗油滴。请决定是否保留 q 记录。");
      } else if (response.record.status === "rejected_crossing_identity") {
        setStage("results");
        setMessage("该记录已因 crossing 身份不一致被阻断，不能进入反演。");
      } else {
        setMessage("crossing 复核结论已保存。");
      }
    } catch (error) {
      setMessage(`保存 crossing 复核失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const acceptRecord = async (kept: boolean) => {
    if (!selectedRecord) return;
    setBusy(true);
    try {
      const nextSession = await desktopApi.normalSelectRecord({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        kept
      });
      setSession(nextSession);
      setMessage(kept ? "本滴 q 已由用户确认保留。" : "本滴 q 已排除。");
    } catch (error) {
      setMessage(`更新记录失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const runInversion = async () => {
    setBusy(true);
    setProgress(null);
    try {
      const response = await desktopApi.normalRunInversion({ session_root: session?.session_root });
      setSession(response.session);
      setInversion(response.inversion);
      setStage("results");
      setProgress(null);
      setMessage(response.inversion.status === "insufficient_eligible_records" ? "有效保留记录不足 3 条，暂不能反演。" : "盲反演完成。");
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

  const jumpTo = (time: number) => {
    const safeTime = Math.max(0, Math.min(duration || metadata?.duration_s || Number.POSITIVE_INFINITY, time));
    if (videoRef.current) {
      videoRef.current.currentTime = safeTime;
    }
    setCurrentTime(safeTime);
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      void video.play();
    } else {
      video.pause();
    }
  };

  const adjustBoundary = (field: "zero_v_start_s" | "zero_v_end_s", delta: number) => {
    setBoundary((current) => {
      const next = clampBoundary({ ...current, [field]: Number((current[field] + delta).toFixed(3)) }, metadata);
      jumpTo(next[field]);
      return next;
    });
  };

  const adjustSelectionTime = (delta: number) => {
    const next = Math.max(0, Math.min(duration || metadata?.duration_s || 0, Number((selectionTime + delta).toFixed(3))));
    setSelectionTime(next);
    jumpTo(next);
  };

  const clientToVideoPoint = (event: MouseEvent<HTMLDivElement>): VideoPoint | null => {
    const video = videoRef.current;
    if (!video || !metadata) return null;
    const rect = video.getBoundingClientRect();
    const sourceWidth = video.videoWidth || metadata.width || rect.width;
    const sourceHeight = video.videoHeight || metadata.height || rect.height;
    const scale = Math.min(rect.width / sourceWidth, rect.height / sourceHeight);
    const displayWidth = sourceWidth * scale;
    const displayHeight = sourceHeight * scale;
    const offsetX = (rect.width - displayWidth) / 2;
    const offsetY = (rect.height - displayHeight) / 2;
    const x = (event.clientX - rect.left - offsetX) / scale;
    const y = (event.clientY - rect.top - offsetY) / scale;
    if (x < 0 || y < 0 || x > sourceWidth || y > sourceHeight) {
      return null;
    }
    return { x, y };
  };

  const videoBoxStyle = (box: VideoBox) => {
    const video = videoRef.current;
    if (!video || !metadata) return {};
    const rect = video.getBoundingClientRect();
    const sourceWidth = video.videoWidth || metadata.width || rect.width;
    const sourceHeight = video.videoHeight || metadata.height || rect.height;
    const scale = Math.min(rect.width / sourceWidth, rect.height / sourceHeight);
    return {
      left: `${(rect.width - sourceWidth * scale) / 2 + box.x * scale}px`,
      top: `${(rect.height - sourceHeight * scale) / 2 + box.y * scale}px`,
      width: `${box.width * scale}px`,
      height: `${box.height * scale}px`
    };
  };

  const onSelectionDown = (event: MouseEvent<HTMLDivElement>) => {
    if (stage !== "target") return;
    const point = clientToVideoPoint(event);
    if (!point) return;
    setDragStart(point);
    setSelectionBox({ x: point.x, y: point.y, width: 1, height: 1 });
  };

  const onSelectionMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!dragStart || stage !== "target") return;
    const point = clientToVideoPoint(event);
    if (!point) return;
    setSelectionBox({
      x: Math.min(dragStart.x, point.x),
      y: Math.min(dragStart.y, point.y),
      width: Math.max(1, Math.abs(point.x - dragStart.x)),
      height: Math.max(1, Math.abs(point.y - dragStart.y))
    });
  };

  const endSelection = () => {
    setDragStart(null);
    if (selectionBox && (selectionBox.width < 4 || selectionBox.height < 4)) {
      setMessage("框选区域太小，请拖出一个包住油滴的矩形。");
    }
  };

  const buildParameterOverrides = () => {
    const physics: Record<string, number> = {};
    const gridOverrides: Record<string, number> = {};
    for (const [key, raw] of Object.entries(parameterOverrides)) {
      const value = Number(raw);
      if (!Number.isFinite(value)) continue;
      if (physicsKeys.includes(key)) {
        physics[key] = value;
      } else if (gridKeys.includes(key)) {
        gridOverrides[key] = value;
      }
    }
    return {
      ...(Object.keys(physics).length ? { physics } : {}),
      ...(Object.keys(gridOverrides).length ? { grid: gridOverrides } : {})
    };
  };

  const configValue = (key: string) => {
    if (parameterOverrides[key] !== undefined) {
      return parameterOverrides[key];
    }
    const source = physicsKeys.includes(key) ? backendConfig?.physics : backendConfig?.grid;
    const value = source?.[key];
    return value === undefined || value === null ? "" : String(value);
  };

  const canAcceptRecord =
    selectedRecord?.status === "pending_user_confirmation" &&
    Boolean(selectedRecord.q_valid) &&
    (selectedRecord.crossings?.length ? allCrossingsReviewedSame : true);

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

      <main className="normal-flow">
        <aside className="normal-rail panel">
          <div className="section-heading">
            <span>workflow</span>
            <strong>Normal 状态机</strong>
          </div>
          <div className="normal-stage-list">
            {stages.map((item, index) => (
              <button key={item.id} className={item.id === stage ? "normal-stage active" : "normal-stage"} onClick={() => setStage(item.id)} disabled={item.id !== "results" && item.id !== stage}>
                <span>{index + 1}</span>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
          <ProgressBox progress={progress} busy={busy} />
        </aside>

        <section className="normal-video-panel panel" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
          <div className="normal-video-shell">
            {videoUrl ? (
              <>
                <video
                  ref={videoRef}
                  src={videoUrl}
                  onLoadedMetadata={(event) => {
                    setDuration(event.currentTarget.duration || metadata?.duration_s || 0);
                    setCurrentTime(event.currentTarget.currentTime || 0);
                  }}
                  onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                />
                <div className="normal-video-overlay" onMouseDown={onSelectionDown} onMouseMove={onSelectionMove} onMouseUp={endSelection} onMouseLeave={endSelection}>
                  {boundary.zero_v_start_s <= (duration || 0) ? <span className="time-marker start" style={{ left: `${((boundary.zero_v_start_s || 0) / Math.max(0.001, duration || metadata?.duration_s || 1)) * 100}%` }} /> : null}
                  {boundary.zero_v_end_s <= (duration || 0) ? <span className="time-marker end" style={{ left: `${((boundary.zero_v_end_s || 0) / Math.max(0.001, duration || metadata?.duration_s || 1)) * 100}%` }} /> : null}
                  {selectionBox ? <span className="selection-box" style={videoBoxStyle(selectionBox)} /> : null}
                </div>
              </>
            ) : (
              <div className="normal-video-placeholder">
                <FileVideo size={44} />
                <span>拖入视频或选择文件</span>
              </div>
            )}
          </div>
          <div className="normal-player">
            <button className="icon-button step-button step-button--coarse" onClick={() => jumpTo(currentTime - 1)} disabled={!videoUrl} aria-label="后退 1 秒" title="后退 1 秒">
              <StepBack size={16} />
              <span className="step-badge">1s</span>
            </button>
            <button className="icon-button step-button step-button--fine" onClick={() => jumpTo(currentTime - 0.1)} disabled={!videoUrl} aria-label="后退 0.1 秒" title="后退 0.1 秒">
              <ChevronsLeft size={16} />
              <span className="step-badge">0.1</span>
            </button>
            <button className="icon-button" onClick={togglePlay} disabled={!videoUrl} aria-label={isPlaying ? "暂停" : "播放"}>
              {isPlaying ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <button className="icon-button step-button step-button--fine" onClick={() => jumpTo(currentTime + 0.1)} disabled={!videoUrl} aria-label="前进 0.1 秒" title="前进 0.1 秒">
              <ChevronsRight size={16} />
              <span className="step-badge">0.1</span>
            </button>
            <button className="icon-button step-button step-button--coarse" onClick={() => jumpTo(currentTime + 1)} disabled={!videoUrl} aria-label="前进 1 秒" title="前进 1 秒">
              <StepForward size={16} />
              <span className="step-badge">1s</span>
            </button>
            <input
              className="normal-scrubber"
              type="range"
              min={0}
              max={duration || metadata?.duration_s || 0}
              step={0.01}
              value={currentTime}
              disabled={!videoUrl}
              onChange={(event) => jumpTo(Number(event.target.value))}
              aria-label="视频进度"
            />
            <span>{formatFixed(currentTime, 2)} / {formatFixed(duration || metadata?.duration_s, 2)} s</span>
          </div>
        </section>

        <aside className="normal-inspector panel">
          {stage === "import" ? (
            <ImportPanel
              videoPath={videoPath}
              metadata={metadata}
              busy={busy}
              onPath={setVideoPath}
              onInspect={() => inspectVideo(videoPath)}
              onOpen={openVideo}
              onStart={startPrepare}
            />
          ) : null}
          {stage === "boundary" ? (
            <BoundaryPanel
              boundary={boundary}
              metadata={metadata}
              diagnostics={boundaryDiagnostics}
              grid={grid}
              onBoundary={setBoundary}
              onAdjust={adjustBoundary}
              onJump={jumpTo}
              onConfirm={confirmBoundary}
              busy={busy}
            />
          ) : null}
          {stage === "target" ? (
            <TargetPanel
              selectionTime={selectionTime}
              selectionBox={selectionBox}
              balanceVoltage={balanceVoltage}
              balanceConfirmed={balanceConfirmed}
              advancedOpen={advancedOpen}
              parameterKeys={[...physicsKeys, ...gridKeys]}
              configValue={configValue}
              overrides={parameterOverrides}
              onSelectionTime={setSelectionTime}
              onAdjustSelection={adjustSelectionTime}
              onJump={jumpTo}
              onVoltage={setBalanceVoltage}
              onBalanceConfirmed={setBalanceConfirmed}
              onAdvancedOpen={setAdvancedOpen}
              onOverride={(key, value) => setParameterOverrides((current) => ({ ...current, [key]: value }))}
              onTrack={selectTargetAndTrack}
              busy={busy}
            />
          ) : null}
          {stage === "review" ? (
            <ReviewPanel
              record={selectedRecord}
              reviewEvent={reviewEvent}
              reviewVideoRef={reviewVideoRef}
              onPrepareReview={prepareCrossingReview}
              onReview={submitCrossingReview}
              onContinue={() => setStage("results")}
              busy={busy}
            />
          ) : null}
          {stage === "results" ? (
            <ResultsPanel
              session={session}
              selectedRecord={selectedRecord}
              inversion={inversion ?? session?.inversion ?? null}
              canAcceptRecord={canAcceptRecord}
              keptValidCount={keptValidCount}
              onSelectRecord={setSelectedRecordId}
              onAccept={() => acceptRecord(true)}
              onReject={() => acceptRecord(false)}
              onRunInversion={runInversion}
              busy={busy}
            />
          ) : null}
        </aside>
      </main>

      <div className="normal-evidence-strip">
        <InfoTile label="Session" value={session?.session_id ? String(session.session_id) : "new"} />
        <InfoTile label="元数据" value={metadata ? `${metadata.width}x${metadata.height} / ${formatFixed(metadata.fps)} fps / ${formatFixed(metadata.duration_s)} s` : "未导入"} />
        <InfoTile label="网格" value={grid ? `${gridLineCount} lines, ${formatSci(grid.scale_y_m_per_px, 2)} m/px` : "未检测"} />
        <InfoTile label="有效区域" value={grid ? `${formatFixed(effectiveTopPx, 0)} px - ${formatFixed(effectiveBottomPx, 0)} px` : "未检测"} />
        <InfoTile label="记录" value={`${session?.counts?.total ?? 0} total / ${keptValidCount} accepted`} />
      </div>

      <div className="status-toast" role="status">
        {busy ? progress?.label ?? "正在处理..." : message}
      </div>
    </div>
  );
}

function ProgressBox({ progress, busy }: { progress: NormalProgressEvent | null; busy: boolean }) {
  const percent = typeof progress?.fraction === "number" ? Math.round(progress.fraction * 100) : null;
  return (
    <div className="normal-progress-box">
      <span>{busy ? "processing" : "idle"}</span>
      <strong>{progress?.label ?? "等待操作"}</strong>
      <div className="normal-progress-track">
        <i style={{ width: percent === null ? "34%" : `${percent}%` }} className={percent === null ? "indeterminate" : ""} />
      </div>
      <small>
        {percent === null
          ? progress?.indeterminate
            ? "真实阶段，无可量化百分比"
            : "-"
          : `${percent}% · ${progress?.current ?? "-"} / ${progress?.total ?? "-"} ${progress?.unit ?? ""}`}
      </small>
    </div>
  );
}

function ImportPanel(props: {
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
        <span>stage 1</span>
        <strong>导入与视频预览</strong>
      </div>
      <div className="normal-path-row">
        <input value={props.videoPath} onChange={(event) => props.onPath(event.target.value)} placeholder="拖入视频或粘贴绝对路径" />
        <button className="ghost-button" onClick={props.onOpen}>
          <FolderOpen size={16} />
          选择
        </button>
      </div>
      <div className="normal-meta-grid">
        <InfoTile label="FPS" value={formatFixed(props.metadata?.fps)} />
        <InfoTile label="帧数" value={formatFixed(props.metadata?.frame_count, 0)} />
        <InfoTile label="分辨率" value={props.metadata ? `${props.metadata.width} x ${props.metadata.height}` : "-"} />
        <InfoTile label="时长" value={`${formatFixed(props.metadata?.duration_s)} s`} />
      </div>
      <button className="ghost-button full" disabled={props.busy || !props.videoPath} onClick={props.onInspect}>
        <Video size={16} />
        只预览 metadata
      </button>
      <button className="primary-button full" disabled={props.busy || !props.metadata?.readable} onClick={props.onStart}>
        <Play size={16} />
        开始处理
      </button>
    </div>
  );
}

function BoundaryPanel(props: {
  boundary: NormalBoundary;
  metadata: VideoMetadata | null;
  diagnostics: Record<string, unknown> | null;
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
        <span>stage 2</span>
        <strong>0V 边界确认</strong>
      </div>
      {(["zero_v_start_s", "zero_v_end_s"] as const).map((field) => (
        <div className="normal-boundary-editor" key={field}>
          <label>{field === "zero_v_start_s" ? "0V start (s)" : "0V end (s)"}</label>
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
            <button onClick={() => props.onJump(props.boundary[field])}>跳转</button>
          </div>
        </div>
      ))}
      <div className="normal-diagnostic-box">
        <strong>自动建议</strong>
        <span>source: {props.boundary.source ?? "unknown"}</span>
        <span>flags: {(props.boundary.flags ?? []).join(", ") || "none"}</span>
        <span>operations: {Array.isArray(props.diagnostics?.operations) ? props.diagnostics?.operations.length : 0}</span>
      </div>
      <div className="normal-diagnostic-box">
        <strong>网格</strong>
        <span>valid: {String(props.grid?.valid ?? false)}</span>
        <span>scale_y: {formatSci(props.grid?.scale_y_m_per_px, 2)} m/px</span>
      </div>
      <button className="primary-button full" disabled={props.busy || !props.grid?.valid} onClick={props.onConfirm}>
        <Check size={16} />
        确认边界
      </button>
    </div>
  );
}

function TargetPanel(props: {
  selectionTime: number;
  selectionBox: VideoBox | null;
  balanceVoltage: string;
  balanceConfirmed: boolean;
  advancedOpen: boolean;
  parameterKeys: string[];
  configValue: (key: string) => string;
  overrides: Record<string, string>;
  busy: boolean;
  onSelectionTime: (time: number) => void;
  onAdjustSelection: (delta: number) => void;
  onJump: (time: number) => void;
  onVoltage: (value: string) => void;
  onBalanceConfirmed: (value: boolean) => void;
  onAdvancedOpen: (value: boolean) => void;
  onOverride: (key: string, value: string) => void;
  onTrack: () => void;
}) {
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <span>stage 3</span>
        <strong>框选目标油滴</strong>
      </div>
      <div className="normal-boundary-editor">
        <label>selection time (s)</label>
        <div className="normal-step-row compact">
          <button onClick={() => props.onAdjustSelection(-1)}>-1s</button>
          <button onClick={() => props.onAdjustSelection(-0.1)}>-0.1s</button>
          <input
            type="number"
            step="0.1"
            value={props.selectionTime}
            onChange={(event) => {
              const value = Number(event.target.value);
              props.onSelectionTime(value);
              props.onJump(value);
            }}
          />
          <button onClick={() => props.onAdjustSelection(0.1)}>+0.1s</button>
          <button onClick={() => props.onAdjustSelection(1)}>+1s</button>
        </div>
      </div>
      <div className="normal-diagnostic-box">
        <strong>矩形框选</strong>
        <span>{props.selectionBox ? `x=${formatFixed(props.selectionBox.x, 1)}, y=${formatFixed(props.selectionBox.y, 1)}, w=${formatFixed(props.selectionBox.width, 1)}, h=${formatFixed(props.selectionBox.height, 1)}` : "在视频画面上拖拽一个矩形包住油滴"}</span>
      </div>
      <label className="normal-field">
        <span>平衡电压 V</span>
        <input value={props.balanceVoltage} onChange={(event) => props.onVoltage(event.target.value)} placeholder="例如 239" inputMode="decimal" />
      </label>
      <label className="normal-checkline">
        <input type="checkbox" checked={props.balanceConfirmed} onChange={(event) => props.onBalanceConfirmed(event.target.checked)} />
        <span>我确认该油滴在输入电压下处于平衡或近似静止状态</span>
      </label>
      <button className="ghost-button full" onClick={() => props.onAdvancedOpen(!props.advancedOpen)}>
        <RotateCcw size={16} />
        本次测量高级参数
      </button>
      {props.advancedOpen ? (
        <div className="normal-param-grid">
          {props.parameterKeys.map((key) => (
            <label key={key}>
              <span>{key}</span>
              <input value={props.configValue(key)} onChange={(event) => props.onOverride(key, event.target.value)} />
              <small>{props.overrides[key] === undefined ? "backend default" : "override for this record"}</small>
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

function ReviewPanel(props: {
  record: NormalRecord | null;
  reviewEvent: NormalCrossingEvent | null;
  reviewVideoRef: RefObject<HTMLVideoElement | null>;
  busy: boolean;
  onPrepareReview: (event: NormalCrossingEvent) => void;
  onReview: (result: "same_drop" | "different_drop") => void;
  onContinue: () => void;
}) {
  const crossings = props.record?.crossings ?? [];
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <span>stage 4</span>
        <strong>轨迹与 crossing 复核</strong>
      </div>
      <div className="normal-diagnostic-box">
        <strong>{statusLabel(props.record?.status)}</strong>
        <span>crossings: {crossings.length}</span>
        <span>未复核 crossing 会阻断用户确认。</span>
      </div>
      <div className="normal-crossing-list">
        {crossings.map((event) => (
          <button key={event.event_id} className={props.reviewEvent?.event_id === event.event_id ? "active" : ""} onClick={() => props.onPrepareReview(event)}>
            <Scissors size={14} />
            <span>{event.event_id}</span>
            <small>{formatFixed(event.start_time_s ?? event.time_s, 2)}s · {event.review_result ?? "unreviewed"}</small>
          </button>
        ))}
        {crossings.length === 0 ? <span className="normal-drop-hint">本次追踪没有 crossing，可进入结果确认。</span> : null}
      </div>
      {props.reviewEvent?.review_clip_url ? (
        <div className="normal-review-clip">
          <video ref={props.reviewVideoRef} src={props.reviewEvent.review_clip_url} muted loop controls />
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
      <button className="ghost-button full" disabled={props.record?.status !== "pending_user_confirmation"} onClick={props.onContinue}>
        去确认 q 结果
      </button>
    </div>
  );
}

function ResultsPanel(props: {
  session: NormalSession | null;
  selectedRecord: NormalRecord | null;
  inversion: NormalInversionResult | null;
  canAcceptRecord: boolean;
  keptValidCount: number;
  busy: boolean;
  onSelectRecord: (id: string) => void;
  onAccept: () => void;
  onReject: () => void;
  onRunInversion: () => void;
}) {
  const record = props.selectedRecord;
  const q = (record?.q as Record<string, any> | undefined) ?? {};
  const fit = (record?.fit as Record<string, any> | undefined) ?? {};
  const uncertainty = q.uncertainty_budget as Record<string, any> | undefined;
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <span>stage 5</span>
        <strong>测量结果与 session</strong>
      </div>
      {record ? (
        <>
          <div className="normal-result-hero">
            <span>{statusLabel(record.status)}</span>
            <strong>{formatSci(record.q_C)} C</strong>
            <small>sigma_q = {formatSci(record.sigma_q_C)} C</small>
          </div>
          <div className="normal-meta-grid">
            <InfoTile label="半径" value={`${formatSci(record.radius_m)} m`} />
            <InfoTile label="下落速度" value={`${formatSci(record.fall_velocity_m_s)} m/s`} />
            <InfoTile label="R²" value={formatFixed(fit.r2 as number | undefined, 3)} />
            <InfoTile label="拟合点" value={String(fit.fit_point_count ?? "-")} />
          </div>
          <div className="normal-diagnostic-box">
            <strong>不确定度来源</strong>
            <span>included: {Array.isArray(uncertainty?.included) ? uncertainty.included.map((row: any) => row.component).join(", ") : "-"}</span>
            <span>not included: {Array.isArray(uncertainty?.not_included) ? uncertainty.not_included.join(", ") : "-"}</span>
          </div>
          <div className="panel-actions">
            <button className="primary-button small" disabled={props.busy || !props.canAcceptRecord} onClick={props.onAccept}>
              <Save size={15} />
              确认保留
            </button>
            <button className="ghost-button" disabled={props.busy} onClick={props.onReject}>
              返回调整/排除
            </button>
          </div>
        </>
      ) : (
        <div className="normal-drop-hint">还没有本次测量记录。</div>
      )}
      <div className="normal-record-list">
        {(props.session?.records ?? []).map((item) => (
          <button key={item.record_id} className={item.record_id === record?.record_id ? "active" : ""} onClick={() => props.onSelectRecord(item.record_id)}>
            <span>{item.record_id}</span>
            <strong>{formatSci(item.q_C)}</strong>
            <small>{statusLabel(item.status)}</small>
          </button>
        ))}
      </div>
      <div className="normal-diagnostic-box">
        <strong>盲反演</strong>
        <span>{props.keptValidCount}/3 accepted q</span>
        {props.inversion ? (
          <>
            <span>status: {String(props.inversion.status ?? "-")}</span>
            <span>e: {formatSci(props.inversion.e_hat_C)} C</span>
            <span>flags: {(props.inversion.flags ?? []).join(", ") || "none"}</span>
          </>
        ) : (
          <span>没有真实连续模型时只展示量子化对齐诊断，不输出模型胜负。</span>
        )}
      </div>
      <button className="primary-button full" disabled={props.busy || props.keptValidCount < 3} onClick={props.onRunInversion}>
        <Play size={16} />
        运行 Normal 盲反演
      </button>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="normal-info-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
