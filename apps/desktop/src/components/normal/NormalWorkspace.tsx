import { DragEvent, useEffect, useRef, useState } from "react";
import { FileVideo, RotateCcw, Save, Sparkles, UploadCloud } from "lucide-react";
import type { NormalBoundarySuggestion, NormalGrid, NormalPrepareVideoResponse, NormalRecord, NormalSession, NormalTarget, VideoMetadata } from "../../types";
import { desktopApi } from "../../lib/desktopApi";
import { NormalVideoPlayer } from "./NormalVideoPlayer";
import { BoundaryEditor } from "./BoundaryEditor";
import { CrossingReview } from "./CrossingReview";
import { QRecordManager } from "./QRecordManager";
import { NormalResults } from "./NormalResults";

type Stage = "import" | "boundary" | "target" | "tracking" | "records" | "inversion";

export function NormalWorkspace({ onSwitchMode }: { onSwitchMode: (mode: "normal" | "experimental") => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stage, setStage] = useState<Stage>("import");
  const [session, setSession] = useState<NormalSession | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [balanceVoltage, setBalanceVoltage] = useState("240");
  const [boundary, setBoundary] = useState<NormalBoundarySuggestion | null>(null);
  const [grid, setGrid] = useState<NormalGrid | null>(null);
  const [target, setTarget] = useState<NormalTarget | null>(null);
  const [activeRecord, setActiveRecord] = useState<NormalRecord | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("普通模式会自动保存 session。");
  const [advancedOpen, setAdvancedOpen] = useState(false);

  useEffect(() => {
    desktopApi.normalInitialize().then((result) => {
      setSession(result.session);
      if (result.session.records.length) {
        setStage("records");
        setMessage(`已自动恢复 ${result.session.records.length} 条记录。`);
      }
    }).catch((error) => setMessage(`session 恢复失败：${error instanceof Error ? error.message : String(error)}`));
  }, []);

  const prepareVideo = async (path = videoPath) => {
    if (!path || !Number.isFinite(Number(balanceVoltage)) || Number(balanceVoltage) <= 0) {
      setMessage("请先导入视频并输入正的平衡电压。");
      return;
    }
    setBusy(true);
    try {
      const result: NormalPrepareVideoResponse = await desktopApi.normalPrepareVideo({ video_path: path });
      setVideoPath(result.metadata.path || path);
      setVideoUrl(result.video_url);
      setMetadata(result.metadata);
      setBoundary(result.boundary.suggestion);
      setGrid(result.grid);
      setSession(result.session);
      setStage("boundary");
      setMessage("已生成时间建议，并跳转到适合框选的平衡帧。");
      setTimeout(() => seekFrame(result.boundary.suggestion.selection_frame, result.metadata.fps), 60);
    } catch (error) {
      setMessage(`视频准备失败：${error instanceof Error ? error.message : String(error)}。已保留当前输入。`);
    } finally {
      setBusy(false);
    }
  };

  const openVideo = async () => {
    const path = await desktopApi.openVideoDialog();
    if (path) {
      setVideoPath(path);
      await prepareVideo(path);
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files.item(0) as (File & { path?: string }) | null;
    if (file?.path) {
      setVideoPath(file.path);
      void prepareVideo(file.path);
    }
  };

  const seekFrame = (frame: number, fps = metadata?.fps || 30) => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    setIsPlaying(false);
    video.currentTime = Math.max(0, frame / fps);
    setCurrentTime(video.currentTime);
  };

  const seekBoundary = (kind: "selection" | "start" | "end") => {
    if (!boundary) return;
    const frame = kind === "selection" ? boundary.selection_frame : kind === "start" ? boundary.fall_start_frame : boundary.fall_end_frame;
    seekFrame(frame);
  };

  const nudgeCurrent = (delta: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    setIsPlaying(false);
    video.currentTime = Math.max(0, Math.min(video.duration || Infinity, video.currentTime + delta));
    setCurrentTime(video.currentTime);
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      void video.play();
      setIsPlaying(true);
    } else {
      video.pause();
      setIsPlaying(false);
    }
  };

  const beginTargetSelection = () => {
    if (!boundary) return;
    seekFrame(boundary.selection_frame);
    setIsSelecting(true);
    setStage("target");
    setMessage("在当前真实视频帧上拖拽框选油滴。");
  };

  const onTarget = (next: NormalTarget) => {
    setTarget(next);
    setIsSelecting(false);
    setStage("tracking");
    setMessage(`已保存源像素框选：(${next.source_center.x.toFixed(1)}, ${next.source_center.y.toFixed(1)})，可运行追踪。`);
  };

  const runTracking = async () => {
    if (!target || !boundary || !grid || !metadata) {
      setMessage("缺少框选、边界或网格信息。请回到上一步修正。");
      return;
    }
    setBusy(true);
    try {
      const result = await desktopApi.normalSaveMeasurement({
        video_path: videoPath,
        balance_voltage_V: Number(balanceVoltage),
        target,
        boundary,
        grid,
        balance_verified: boundary.selection_frame < boundary.fall_start_frame,
      });
      setActiveRecord(result.record);
      setSession(result.session);
      setStage("records");
      setMessage(result.record.status === "valid" ? "已保存有效 q。可以继续测量或查看记录。" : `已保存为诊断记录：${(result.record.recovery_suggestions ?? ["请重新测量。"])[0]}`);
    } catch (error) {
      setMessage(`追踪失败：${error instanceof Error ? error.message : String(error)}。框选和边界已保留，可修改后重试。`);
    } finally {
      setBusy(false);
    }
  };

  const measureAnother = () => {
    setTarget(null);
    setActiveRecord(null);
    setStage("target");
    beginTargetSelection();
  };

  const importNew = () => {
    setTarget(null);
    setActiveRecord(null);
    setBoundary(null);
    setGrid(null);
    setVideoPath("");
    setVideoUrl("");
    setMetadata(null);
    setStage("import");
    setMessage("可以导入新视频，已有记录已自动保存。");
  };

  const runInversion = async () => {
    setBusy(true);
    try {
      const result = await desktopApi.normalRunInversion();
      setSession(result.session);
      setStage("inversion");
      setMessage("双算法反演已完成。");
    } catch (error) {
      setMessage(`反演失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const exportSession = async () => {
    const result = await desktopApi.normalExportSession();
    setMessage(JSON.stringify(result).includes("canceled") ? "已取消导出。" : "报告包已导出。");
  };

  const createQaFixture = async () => {
    const result = await desktopApi.normalCreateQaFixture();
    setSession(result.session);
    setMessage("已创建 QA fixture session。它只用于界面和报告验收，不代表真实视频数据。");
  };

  return (
    <div className="desktop-frame normal-frame">
      <header className="normal-topbar">
        <div>
          <strong>Millikan AI</strong>
          <span>Normal balance-fall mode</span>
        </div>
        <nav className="segmented">
          <button className="active">普通模式</button>
          <button onClick={() => onSwitchMode("experimental")}>Experimental</button>
        </nav>
      </header>

      <main className="normal-workspace">
        <section className="normal-progress">
          {["导入", "边界", "框选", "追踪", "记录", "反演"].map((label, index) => (
            <div key={label} className={index <= stageIndex(stage) ? "done" : ""}>
              <span>{index + 1}</span>
              <small>{label}</small>
            </div>
          ))}
        </section>

        {stage === "import" && (
          <section className="normal-step-card normal-import" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
            <div className="normal-step-heading">
              <span>1</span>
              <div>
                <h2>导入视频并输入平衡电压</h2>
                <p>打开或拖入视频，普通模式会自动检查视频、建议时间边界并保存 session。</p>
              </div>
            </div>
            <div className="normal-import-grid">
              <div className="normal-drop-target"><UploadCloud size={36} /><strong>拖入视频</strong></div>
              <input value={videoPath} onChange={(event) => setVideoPath(event.target.value)} placeholder="视频路径" aria-label="普通模式视频路径" />
              <input value={balanceVoltage} onChange={(event) => setBalanceVoltage(event.target.value)} placeholder="平衡电压 V" aria-label="平衡电压" type="number" />
            </div>
            <div className="panel-actions">
              <button className="ghost-button" onClick={openVideo}><FileVideo size={16} /> 打开文件</button>
              <button className="primary-button" disabled={busy} onClick={() => prepareVideo()}><Sparkles size={16} /> 生成时间建议</button>
            </div>
          </section>
        )}

        {videoUrl && (
          <NormalVideoPlayer
            videoRef={videoRef}
            videoUrl={videoUrl}
            metadata={metadata}
            currentTime={currentTime}
            isPlaying={isPlaying}
            boundary={boundary}
            grid={grid}
            target={target}
            activeRecord={activeRecord}
            selecting={isSelecting}
            onLoadedMetadata={() => boundary && seekFrame(boundary.selection_frame)}
            onTimeUpdate={setCurrentTime}
            onTogglePlay={togglePlay}
            onNudge={nudgeCurrent}
            onSeekBoundary={seekBoundary}
            onTarget={onTarget}
          />
        )}

        {stage === "boundary" && boundary && (
          <>
            <BoundaryEditor boundary={boundary} grid={grid} fps={metadata?.fps || 30} onBoundary={setBoundary} onSeek={seekBoundary} />
            <button className="primary-button stage-primary" onClick={beginTargetSelection}>确认时间，框选油滴</button>
          </>
        )}

        {stage === "target" && (
          <section className="normal-step-card">
            <div className="normal-step-heading">
              <span>3</span>
              <div>
                <h3>框选油滴</h3>
                <p>{target ? "框选已保存，可重新框选或继续追踪。" : "请直接在视频画面上拖拽框选目标油滴。"}</p>
              </div>
            </div>
            <button className="primary-button" onClick={() => setIsSelecting(true)}>{target ? "重新框选" : "开始框选"}</button>
            {target && <button className="primary-button stage-primary" onClick={() => setStage("tracking")}>继续追踪</button>}
          </section>
        )}

        {stage === "tracking" && (
          <section className="normal-step-card">
            <div className="normal-step-heading">
              <span>4</span>
              <div>
                <h3>运行并复核追踪</h3>
                <p>追踪会从框选帧开始，但只从 0V 下落开始帧拟合速度。</p>
              </div>
            </div>
            <button className="primary-button stage-primary" disabled={busy || !target} onClick={runTracking}><Save size={16} /> 运行追踪并保存 q</button>
          </section>
        )}

        <CrossingReview videoRef={videoRef} record={activeRecord} metadata={metadata} />
        <QRecordManager
          session={session}
          activeRecord={activeRecord}
          onSelectRecord={(record) => {
            setActiveRecord(record);
            setMessage(record.status === "valid" ? "正在查看有效记录。" : `诊断记录：${(record.recovery_suggestions ?? ["可重新测量。"])[0]}`);
          }}
          onToggleSelected={async (record, selected) => {
            const result = await desktopApi.normalSelectRecord({ record_id: record.record_id, selected });
            setSession(result.session);
          }}
          onMeasureAnother={measureAnother}
          onImportNew={importNew}
          onRunInversion={runInversion}
        />
        <NormalResults session={session} onExport={exportSession} onCreateQaFixture={createQaFixture} />

        <details className="advanced-diagnostics" open={advancedOpen} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
          <summary>高级诊断</summary>
          <div className="qa-fixture-panel">
            <div>
              <strong>QA fixture session</strong>
              <span>仅用于 packaged GUI、报告和反演界面验收，不作为真实视频测量证据。</span>
            </div>
            <button className="ghost-button" onClick={createQaFixture}>创建 QA fixture</button>
          </div>
          <pre>{JSON.stringify({ boundary, grid, target, activeRecord, sessionCounts: session?.counts }, null, 2)}</pre>
        </details>
      </main>
      <div className="status-toast" role="status">{busy ? "处理中..." : message}</div>
    </div>
  );
}

function stageIndex(stage: Stage): number {
  return { import: 0, boundary: 1, target: 2, tracking: 3, records: 4, inversion: 5 }[stage];
}
