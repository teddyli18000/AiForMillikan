import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronsLeft, ChevronsRight, Download, FileVideo, FolderOpen, Pause, Play, StepBack, StepForward } from "lucide-react";
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
import { fmtScientific } from "../../lib/format";
import type { VideoBox, VideoPoint } from "./videoGeometry";
import {
  fixedOrDash,
  gridParameterKeys,
  physicsParameterKeys,
  selectionWindowFromBoundary,
  stageSteps,
  type MeasurementStage
} from "./workspaceModel";
import { BoundaryPanel, ImportPanel, InfoTile, ProgressBox, ResultsPanel, ReviewPanel, TargetPanel } from "./MeasurementPanels";
import { QCalculationFlow } from "./ChargeFlow";
import { InversionPanel, NormalInversionDashboard } from "./InversionView";
import { TrackFramePlayer } from "./FramePlayers";
import { useVideoControls } from "./videoControls";
import { useRecordRestore } from "./recordRestore";
import { useMeasurementActions } from "./measurementActions";
import type { WorkspaceDesk } from "./workspaceDesk";

export function NormalWorkspace() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const [stage, setStage] = useState<MeasurementStage>("import");
  const [session, setSession] = useState<NormalSession | null>(null);
  const [defaultParameters, setDefaultParameters] = useState<Record<string, any> | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [boundary, setBoundary] = useState<NormalBoundary>({ zero_v_start_s: 0, zero_v_end_s: 1, source: "manual_ui" });
  const [boundaryEdited, setBoundaryEdited] = useState(false);
  const [grid, setGrid] = useState<NormalGrid | null>(null);
  const [selectionTime, setSelectionTime] = useState(0);
  const [selectionBox, setSelectionBox] = useState<VideoBox | null>(null);
  const [selectionAnchor, setSelectionAnchor] = useState<VideoPoint | null>(null);
  const [balanceVoltage, setBalanceVoltage] = useState("");
  const [balanceConfirmed, setBalanceConfirmed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [overrideFields, setOverrideFields] = useState<Record<string, string>>({});
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [retrySourceRecordId, setRetrySourceRecordId] = useState<string | null>(null);
  const [currentCrossing, setCurrentCrossing] = useState<NormalCrossingEvent | null>(null);
  const [inversion, setInversion] = useState<NormalInversionResult | null>(null);
  const [progress, setProgress] = useState<NormalProgressEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [nextDropDialogOpen, setNextDropDialogOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    desktopApi
      .normalInitialize({})
      .then((result) => {
        if (!alive) return;
        setSession(result.session);
        setDefaultParameters(result.config);
      })
      .catch((error) => setMessage(`初始化失败：${error instanceof Error ? error.message : String(error)}`));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => desktopApi.onNormalProgress((event) => setProgress(event)), []);

  useEffect(() => {
    if (stage === "inversion") {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
  }, [stage]);
  const selectedRecord = useMemo(
    () => session?.records.find((record) => record.record_id === selectedRecordId) ?? session?.records[session.records.length - 1] ?? null,
    [selectedRecordId, session?.records]
  );
  const retrySourceRecord = useMemo(
    () => (retrySourceRecordId ? session?.records.find((record) => record.record_id === retrySourceRecordId) ?? null : null),
    [retrySourceRecordId, session?.records]
  );
  const crossings = selectedRecord?.crossings ?? [];
  const allCrossingsSameDrop = crossings.every((event) => event.review_result === "same_drop");
  const keptValidCount = session?.counts?.kept_valid ?? 0;
  const gridLineCount = (grid?.grid_lines_y as unknown[] | undefined)?.length ?? (grid?.line_y_px as unknown[] | undefined)?.length ?? 0;
  const effectiveTopPx = Number(grid?.effective_top_px ?? grid?.second_line_y ?? Number.NaN);
  const effectiveBottomPx = Number(grid?.effective_bottom_px ?? grid?.penultimate_line_y ?? Number.NaN);
  const selectionWindow = selectionWindowFromBoundary(boundary, metadata);
  const selectedOverlayUrl =
    selectedRecord?.artifact_urls?.overlay_mp4 ??
    selectedRecord?.artifact_urls?.single_droplet_overlay_mp4 ??
    "";
  const playerStartS = stage === "target" ? selectionWindow.start_s : 0;
  const playerEndS = stage === "target" ? selectionWindow.end_s : duration || metadata?.duration_s || 0;
  const selectedTrackFrames = selectedRecord?.track_review_frames ?? [];
  const inReviewOrResults = stage === "review" || stage === "results";
  const showingTrackFrames = Boolean(inReviewOrResults && selectedTrackFrames.length);
  const mainVideoUrl = showingTrackFrames ? "" : inReviewOrResults ? selectedOverlayUrl || videoUrl : videoUrl;
  const showingTrackOverlay = Boolean(inReviewOrResults && selectedOverlayUrl && !showingTrackFrames);
  const canKeepRecord =
    selectedRecord?.status === "pending_user_confirmation" &&
    Boolean(selectedRecord.q_valid) &&
    (selectedRecord.crossings?.length ? allCrossingsSameDrop : true);

  const desk: WorkspaceDesk = {
    videoRef,
    overlayRef,
    stage,
    setStage,
    session,
    setSession,
    defaultParameters,
    setDefaultParameters,
    metadata,
    setMetadata,
    videoPath,
    setVideoPath,
    videoUrl,
    setVideoUrl,
    boundary,
    setBoundary,
    boundaryEdited,
    setBoundaryEdited,
    grid,
    setGrid,
    selectionTime,
    setSelectionTime,
    selectionBox,
    setSelectionBox,
    selectionAnchor,
    setSelectionAnchor,
    balanceVoltage,
    setBalanceVoltage,
    balanceConfirmed,
    setBalanceConfirmed,
    advancedOpen,
    setAdvancedOpen,
    overrideFields,
    setOverrideFields,
    selectedRecordId,
    setSelectedRecordId,
    retrySourceRecordId,
    setRetrySourceRecordId,
    currentCrossing,
    setCurrentCrossing,
    inversion,
    setInversion,
    progress,
    setProgress,
    busy,
    setBusy,
    message,
    setMessage,
    isPlaying,
    setIsPlaying,
    currentTime,
    setCurrentTime,
    duration,
    setDuration,
    nextDropDialogOpen,
    setNextDropDialogOpen,
    selectedRecord,
    retrySourceRecord,
    crossings,
    allCrossingsSameDrop,
    keptValidCount,
    gridLineCount,
    effectiveTopPx,
    effectiveBottomPx,
    selectionWindow,
    selectedOverlayUrl,
    playerStartS,
    playerEndS,
    selectedTrackFrames,
    inReviewOrResults,
    showingTrackFrames,
    mainVideoUrl,
    showingTrackOverlay,
    canKeepRecord
  };

  const video = useVideoControls(desk);
  const restore = useRecordRestore(desk, video);
  const actions = useMeasurementActions(desk, video, restore);
  const {
    inspectVideo, openVideo, onDrop, startPrepare, confirmBoundary, selectTargetAndTrack,
    prepareCrossingReview, submitCrossingReview, acceptRecord, runInversion, exportSession,
    seekVideoTo, jumpTo, playerJumpTo, togglePlay, setSelectionFrameTime, adjustBoundary,
    adjustSelectionTime, onSelectionDown, onSelectionMove, endSelection, videoBoxStyle,
    parameterInputValue, noteBoundaryEdit, nextDropSameVideo,
    nextDropDifferentVideo, backToBoundary, backToTarget, onLoadedMetadata, onTimeUpdate
  } = { ...video, ...restore, ...actions };

  return (
    <div className="desktop-frame normal-workspace">
      <header className="normal-topbar">
        <div className="topbar__brand">
          <strong>密立根油滴实验</strong>
          <span>单滴电荷测量</span>
        </div>
        <div className="normal-topbar__actions">
          <button className="ghost-button" onClick={openVideo}>
            <FolderOpen size={16} />
            选择视频
          </button>
          <button className="ghost-button" disabled={!session?.session_root} onClick={exportSession}>
            <Download size={16} />
            导出报告
          </button>
          <button className="primary-button small" disabled={busy || keptValidCount < 3} onClick={runInversion} title={keptValidCount < 3 ? "保留至少三条有效记录后，可估计元电荷" : "估计元电荷"}>
            <Play size={16} />
            估计元电荷
          </button>
        </div>
      </header>

      <main className={`normal-flow normal-flow--${stage}`}>
        <nav className="normal-rail panel" aria-label="测量流程">
          <div className="section-heading normal-rail-heading">
            <strong>测量流程</strong>
          </div>
          <div className="normal-stage-list">
            {stageSteps.map((item, index) => (
              <button
                key={item.id}
                className={item.id === stage ? "normal-stage active" : "normal-stage"}
                aria-current={item.id === stage ? "step" : undefined}
                onClick={() => setStage(item.id)}
                disabled={item.id !== "results" && item.id !== stage && !(item.id === "inversion" && Boolean(inversion ?? session?.inversion))}
              >
                <span>{index + 1}</span>
                <strong>{item.title}</strong>
              </button>
            ))}
          </div>
        </nav>

        <section className={stage === "inversion" ? "normal-video-panel panel normal-video-panel--inversion" : "normal-video-panel panel"} onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
          {stage === "inversion" ? (
            <NormalInversionDashboard inversion={inversion ?? session?.inversion ?? null} records={session?.records ?? []} />
          ) : (
            <>
              <div className={showingTrackFrames ? "normal-video-shell normal-video-shell--review" : "normal-video-shell"}>
                {showingTrackFrames ? (
                  <TrackFramePlayer frames={selectedTrackFrames} />
                ) : mainVideoUrl ? (
                  <>
                    <video
                      ref={videoRef}
                      src={mainVideoUrl}
                      onLoadedMetadata={onLoadedMetadata}
                      onTimeUpdate={onTimeUpdate}
                      onPlay={() => setIsPlaying(true)}
                      onPause={() => setIsPlaying(false)}
                    />
                    {showingTrackOverlay ? <div className="normal-overlay-badge">轨迹回放</div> : null}
                    {stage === "target" ? <div className="normal-overlay-badge normal-overlay-badge--selection">框选时刻 {fixedOrDash(selectionTime, 2)} s</div> : null}
                    {stage === "target" ? (
                      <div ref={overlayRef} className="normal-video-overlay" onMouseDown={onSelectionDown} onMouseMove={onSelectionMove} onMouseUp={endSelection} onMouseLeave={endSelection}>
                        {selectionBox ? <span className="selection-box" style={videoBoxStyle(selectionBox)} /> : null}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="normal-video-placeholder">
                    <FileVideo size={44} />
                    <span>拖入视频或选择文件</span>
                  </div>
                )}
              </div>
              {!showingTrackFrames ? <div className="normal-player">
                <button className="icon-button step-button step-button--coarse" onClick={() => playerJumpTo((stage === "target" ? selectionTime : currentTime) - 1)} disabled={!mainVideoUrl} aria-label="后退 1 秒" title="后退 1 秒">
                  <StepBack size={16} />
                  <span className="step-badge">1s</span>
                </button>
                <button className="icon-button step-button step-button--fine" onClick={() => playerJumpTo((stage === "target" ? selectionTime : currentTime) - 0.1)} disabled={!mainVideoUrl} aria-label="后退 0.1 秒" title="后退 0.1 秒">
                  <ChevronsLeft size={16} />
                  <span className="step-badge">0.1</span>
                </button>
                <button className="icon-button" onClick={togglePlay} disabled={!mainVideoUrl} aria-label={isPlaying ? "暂停" : "播放"}>
                  {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <button className="icon-button step-button step-button--fine" onClick={() => playerJumpTo((stage === "target" ? selectionTime : currentTime) + 0.1)} disabled={!mainVideoUrl} aria-label="前进 0.1 秒" title="前进 0.1 秒">
                  <ChevronsRight size={16} />
                  <span className="step-badge">0.1</span>
                </button>
                <button className="icon-button step-button step-button--coarse" onClick={() => playerJumpTo((stage === "target" ? selectionTime : currentTime) + 1)} disabled={!mainVideoUrl} aria-label="前进 1 秒" title="前进 1 秒">
                  <StepForward size={16} />
                  <span className="step-badge">1s</span>
                </button>
                <div className="normal-timeline">
                  <input
                    className="normal-scrubber"
                    type="range"
                    min={playerStartS}
                    max={playerEndS}
                    step={0.01}
                    value={stage === "target" ? selectionTime : currentTime}
                    disabled={!mainVideoUrl}
                    onChange={(event) => playerJumpTo(Number(event.target.value))}
                    aria-label="视频进度"
                  />
                  {(["zero_v_start_s", "zero_v_end_s"] as const).map((key) => boundary[key] >= playerStartS && boundary[key] <= playerEndS && playerEndS > playerStartS ? (
                    <span key={key} className={`normal-timeline-marker ${key === "zero_v_end_s" ? "end" : "start"}`} style={{ left: `${(boundary[key] - playerStartS) / (playerEndS - playerStartS) * 100}%` }} />
                  ) : null)}
                </div>
                <span>{fixedOrDash(currentTime, 2)} / {fixedOrDash(duration || metadata?.duration_s, 2)} s</span>
              </div> : null}
            </>
          )}
        </section>

        <aside className="normal-inspector panel">
          <ProgressBox progress={progress} busy={busy} />
          {!busy && message ? <p className="normal-status" role="status">{message}</p> : null}
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
              grid={grid}
              onBoundary={noteBoundaryEdit}
              onAdjust={adjustBoundary}
              onJump={jumpTo}
              onConfirm={confirmBoundary}
              busy={busy}
            />
          ) : null}
          {stage === "target" ? (
            <TargetPanel
              selectionTime={selectionTime}
              selectionWindow={selectionWindow}
              selectionBox={selectionBox}
              balanceVoltage={balanceVoltage}
              balanceConfirmed={balanceConfirmed}
              advancedOpen={advancedOpen}
              parameterKeys={[...physicsParameterKeys, ...gridParameterKeys]}
              parameterInputValue={parameterInputValue}
              overrides={overrideFields}
              onSelectionTime={(time) => setSelectionFrameTime(time)}
              onAdjustSelection={adjustSelectionTime}
              onVoltage={(value) => {
                setBalanceVoltage(value);
                setBalanceConfirmed(false);
              }}
              onBalanceConfirmed={setBalanceConfirmed}
              onAdvancedOpen={setAdvancedOpen}
              onOverride={(key, value) => {
                setOverrideFields((current) => ({ ...current, [key]: value }));
                setSelectedRecordId(null);
                setCurrentCrossing(null);
                setInversion(null);
              }}
              onTrack={selectTargetAndTrack}
              onBackBoundary={() => backToBoundary(retrySourceRecord)}
              busy={busy}
            />
          ) : null}
          {stage === "review" ? (
            <ReviewPanel
              record={selectedRecord}
              currentCrossing={currentCrossing}
              onPrepareReview={prepareCrossingReview}
              onReview={submitCrossingReview}
              onContinue={() => setStage("results")}
              onBackTarget={() => backToTarget(selectedRecord)}
              onBackBoundary={() => backToBoundary(selectedRecord)}
              busy={busy}
            />
          ) : null}
          {stage === "results" ? (
            <ResultsPanel
              session={session}
              selectedRecord={selectedRecord}
              canKeepRecord={canKeepRecord}
              onSelectRecord={setSelectedRecordId}
              onAccept={() => acceptRecord(true)}
              onReject={() => acceptRecord(false)}
              onBackReview={() => {
                if (selectedRecord?.status === "pending_crossing_review") {
                  setCurrentCrossing(null);
                  setStage("review");
                  setMessage("");
                } else {
                  backToTarget(selectedRecord);
                }
              }}
              onBackBoundary={() => backToBoundary(selectedRecord)}
              onNextDrop={() => setNextDropDialogOpen(true)}
              busy={busy}
            />
          ) : null}
          {stage === "inversion" ? (
            <InversionPanel
              session={session}
              inversion={inversion ?? session?.inversion ?? null}
              keptValidCount={keptValidCount}
              onBackResults={() => setStage("results")}
              onNextDrop={() => setNextDropDialogOpen(true)}
              onExport={exportSession}
              onRunInversion={runInversion}
              busy={busy}
            />
          ) : null}
        </aside>
        {stage === "results" && selectedRecord ? (
          <section className="normal-calculation-panel panel"><QCalculationFlow record={selectedRecord} /></section>
        ) : null}
      </main>

      <div className="normal-evidence-strip">
        <InfoTile label="视频" value={metadata ? `${metadata.width} × ${metadata.height} · ${fixedOrDash(metadata.duration_s)} s` : "未导入"} />
        <InfoTile label="网格" value={grid ? `${gridLineCount} 条 · ${fmtScientific(grid.scale_y_m_per_px, 2)} m/px` : "未检测"} />
        <InfoTile label="有效区域" value={grid ? `${fixedOrDash(effectiveTopPx, 0)} px - ${fixedOrDash(effectiveBottomPx, 0)} px` : "未检测"} />
        <InfoTile label="记录" value={`共 ${session?.counts?.total ?? 0} 条，已保留 ${keptValidCount} 条`} />
      </div>

      {nextDropDialogOpen ? (
        <div className="normal-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="next-drop-title">
          <div className="normal-modal">
            <div className="section-heading">
              <strong id="next-drop-title">下一颗油滴</strong>
            </div>
            <p>是否继续使用当前视频？已保留的测量记录不会丢失。</p>
            <div className="panel-actions">
              <button className="primary-button" onClick={nextDropSameVideo}>
                同一个视频
              </button>
              <button className="ghost-button" onClick={nextDropDifferentVideo}>
                换一个视频
              </button>
              <button className="ghost-button" onClick={() => setNextDropDialogOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
