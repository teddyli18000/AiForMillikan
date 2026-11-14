import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, MouseEvent } from "react";
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
import { clientPointToVideoPoint, getContainedVideoMetrics, videoBoxToOverlayStyle } from "./videoGeometry";
import type { VideoBox, VideoPoint } from "./videoGeometry";
import {
  clampBoundary,
  clampSelectionTime,
  fixedOrDash,
  flattenOverrideFields,
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
  const allCrossingsConfirmedSame = crossings.every((event) => event.review_result === "same_drop");
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
  const inTrackPlaybackStage = stage === "review" || stage === "results";
  const showingTrackFrames = Boolean(inTrackPlaybackStage && selectedTrackFrames.length);
  const mainVideoUrl = showingTrackFrames ? "" : inTrackPlaybackStage ? selectedOverlayUrl || videoUrl : videoUrl;
  const showingTrackOverlay = Boolean(inTrackPlaybackStage && selectedOverlayUrl && !showingTrackFrames);

  const inspectVideo = async (path: string) => {
    if (!path) {
      setMessage("请先选择或拖入视频。");
      return;
    }
    setBusy(true);
    setProgress(null);
    try {
      const inspected = await desktopApi.normalInspectVideo({ video_path: path });
      setMetadata(inspected.metadata);
      setVideoPath(inspected.video_path || path);
      setVideoUrl(inspected.video_url);
      setDuration(inspected.metadata.duration_s || 0);
      setBoundary({ zero_v_start_s: 0, zero_v_end_s: Math.min(1, inspected.metadata.duration_s || 1), source: "manual_ui" });
      setBoundaryEdited(false);
      setGrid(null);
      setSelectionBox(null);
      setBalanceVoltage("");
      setBalanceConfirmed(false);
      setOverrideFields({});
      setCurrentTime(0);
      setSelectedRecordId(null);
      setRetrySourceRecordId(null);
      setCurrentCrossing(null);
      setInversion(null);
      setStage("import");
      setMessage("视频已载入，可开始处理。");
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
      const prepared = await desktopApi.normalPrepareVideo({ video_path: videoPath, session_root: session?.session_root });
      setSession(prepared.session);
      setDefaultParameters(prepared.config);
      setMetadata(prepared.metadata);
      setVideoUrl(prepared.video_url || videoUrl);
      setBoundary(clampBoundary(prepared.boundary, prepared.metadata));
      setBoundaryEdited(false);
      setSelectionTime(clampSelectionTime(Number(prepared.boundary.selection_time_s ?? prepared.boundary.zero_v_start_s ?? 0), prepared.boundary, prepared.metadata));
      setGrid(prepared.grid);
      setStage("boundary");
      setProgress(null);
      setMessage("请结合视频确认零电压区间。");
    } catch (error) {
      setMessage(`开始处理失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const confirmBoundary = async () => {
    setBusy(true);
    setProgress(null);
    try {
      const confirmed = await desktopApi.normalConfirmBoundary({ session_root: session?.session_root, boundary });
      setSession(confirmed.session);
      const confirmedBoundary = (confirmed.active_video?.boundary as NormalBoundary | undefined) ?? boundary;
      setBoundary(confirmedBoundary);
      const nextSelectionTime = clampSelectionTime(Number(confirmedBoundary.zero_v_start_s ?? 0), confirmedBoundary, metadata);
      setSelectionTime(nextSelectionTime);
      if (boundaryEdited || Math.abs(nextSelectionTime - selectionTime) > 0.001) {
        setSelectionBox(null);
        setSelectedRecordId(null);
        setCurrentCrossing(null);
        setInversion(null);
      }
      setBoundaryEdited(false);
      seekVideoTo(nextSelectionTime, metadata, true);
      setStage("target");
      setMessage("请在零电压起点附近框选油滴。");
    } catch (error) {
      setMessage(`确认边界失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const selectTargetAndTrack = async () => {
    if (!selectionBox || !metadata) {
      setMessage("需要先拖拽矩形框选油滴。");
      return;
    }
    const voltage = Number(balanceVoltage);
    if (!Number.isFinite(voltage) || voltage <= 0 || !balanceConfirmed) {
      setMessage("请输入正的平衡电压，并确认油滴已平衡。");
      return;
    }
    const safeSelectionTime = clampSelectionTime(selectionTime, boundary, metadata);
    setSelectionFrameTime(safeSelectionTime, { clearDownstream: false });
    const targetFrame = Math.max(0, Math.min(metadata.frame_count - 1, Math.round(safeSelectionTime * (metadata.fps || 1))));
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
        retry_of_record_id: retrySourceRecordId ?? undefined,
        target,
        balance_voltage_V: voltage,
        balance_confirmed: true,
        parameter_overrides: groupOverrideFields()
      });
      const response = await desktopApi.normalSaveMeasurement({ session_root: session?.session_root });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setRetrySourceRecordId(null);
      setStage(response.record.status === "pending_crossing_review" ? "review" : "results");
      setProgress(null);
      setMessage("");
    } catch (error) {
      setMessage(`追踪失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const prepareCrossingReview = async (event: NormalCrossingEvent) => {
    if (!selectedRecord) return;
    setBusy(true);
    setProgress(null);
    try {
      const response = await desktopApi.normalPrepareCrossingReview({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        event_id: event.event_id
      });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setCurrentCrossing(response.event ?? event);
      setMessage("");
    } catch (error) {
      setMessage(`生成复核片段失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const submitCrossingReview = async (result: "same_drop" | "different_drop") => {
    if (!selectedRecord || !currentCrossing) return;
    setBusy(true);
    setProgress(null);
    try {
      const response = await desktopApi.normalReviewCrossing({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        event_id: currentCrossing.event_id,
        result
      });
      setSession(response.session);
      setSelectedRecordId(response.record.record_id);
      setCurrentCrossing(response.record.crossings?.find((event) => event.event_id === currentCrossing.event_id) ?? null);
      if (response.record.status === "pending_user_confirmation") {
        setStage("results");
        setMessage("");
      } else if (response.record.status === "rejected_crossing_identity") {
        setInversion(null);
        await reopenRecordForRetry(response.record, response.session);
        setMessage("油滴不一致，请调整后重新追踪。");
      } else {
        setMessage("复核结论已保存。");
      }
    } catch (error) {
      setMessage(`保存复核结论失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const acceptRecord = async (kept: boolean) => {
    if (!selectedRecord) return;
    setBusy(true);
    setProgress(null);
    try {
      const nextSession = await desktopApi.normalSelectRecord({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        kept
      });
      setSession(nextSession);
      setInversion(null);
      if (!kept) {
        await reopenRecordForRetry(selectedRecord, nextSession);
        setMessage("已恢复原视频，可调整区间后重新追踪。");
      } else {
        setMessage("");
      }
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
      setStage("inversion");
      setProgress(null);
      setMessage(response.inversion.status === "insufficient_eligible_records" ? "有效保留记录不足 3 条，暂不能反演。" : "");
    } catch (error) {
      setMessage(`盲反演失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const exportSession = async () => {
    try {
      const exported = await desktopApi.normalExportSession({ session_root: session?.session_root });
      setMessage((exported as { canceled?: boolean }).canceled ? "已取消导出。" : "实验记录已导出。");
    } catch (error) {
      setMessage(`导出失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const seekVideoTo = (time: number, metadataOverride?: VideoMetadata | null, pause = false) => {
    const safeDuration = metadataOverride?.duration_s || duration || metadata?.duration_s || Number.POSITIVE_INFINITY;
    const safeTime = Math.max(0, Math.min(safeDuration, time));
    if (videoRef.current) {
      if (pause) {
        videoRef.current.pause();
      }
      videoRef.current.currentTime = safeTime;
    }
    setCurrentTime(safeTime);
  };

  const resetMeasurementDraft = () => {
    setSelectionBox(null);
    setSelectedRecordId(null);
    setRetrySourceRecordId(null);
    setCurrentCrossing(null);
    setInversion(null);
    setSelectionAnchor(null);
  };

  const nextDropSameVideo = async () => {
    setBusy(true);
    setProgress(null);
    try {
      const response = await desktopApi.normalStartNextDroplet({ session_root: session?.session_root, record_id: selectedRecord?.record_id, mode: "same_video" });
      const activeVideo = response.active_video as Record<string, any> | null | undefined;
      const nextBoundary = (activeVideo?.boundary as NormalBoundary | undefined) ?? boundary;
      const nextMetadata = (activeVideo?.metadata as VideoMetadata | undefined) ?? metadata;
      const previousOverrides = (activeVideo?.previous_parameter_overrides ?? {}) as Record<string, unknown>;
      setSession(response.session);
      setNextDropDialogOpen(false);
      resetMeasurementDraft();
      setMetadata(nextMetadata ?? null);
      setVideoPath(typeof activeVideo?.path === "string" ? activeVideo.path : videoPath);
      setVideoUrl(typeof activeVideo?.video_url === "string" ? activeVideo.video_url : videoUrl);
      setGrid((activeVideo?.grid as NormalGrid | undefined) ?? grid);
      setBoundary(nextBoundary);
      setBoundaryEdited(false);
      const previousVoltage = activeVideo?.previous_balance_voltage_V;
      setBalanceVoltage(previousVoltage === undefined || previousVoltage === null ? "" : String(previousVoltage));
      setBalanceConfirmed(false);
      setOverrideFields(flattenOverrideFields(previousOverrides));
      const nextSelectionTime = clampSelectionTime(Number(nextBoundary.zero_v_start_s ?? selectionTime), nextBoundary, nextMetadata ?? metadata);
      setSelectionTime(nextSelectionTime);
      seekVideoTo(nextSelectionTime, nextMetadata ?? metadata, true);
      setStage("target");
      setMessage("请重新框选下一颗油滴。");
    } catch (error) {
      setMessage(`准备下一颗油滴失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const nextDropDifferentVideo = async () => {
    setBusy(true);
    setProgress(null);
    try {
      const response = await desktopApi.normalStartNextDroplet({ session_root: session?.session_root, record_id: selectedRecord?.record_id, mode: "different_video" });
      setSession(response.session);
      setNextDropDialogOpen(false);
      resetMeasurementDraft();
      setMetadata(null);
      setVideoPath("");
      setVideoUrl("");
      setBoundary({ zero_v_start_s: 0, zero_v_end_s: 1, source: "manual_ui" });
      setBoundaryEdited(false);
      setGrid(null);
      setSelectionTime(0);
      setBalanceVoltage("");
      setBalanceConfirmed(false);
      setOverrideFields({});
      setCurrentTime(0);
      setDuration(0);
      setStage("import");
      setMessage("测量记录已保留，请导入下一段视频。");
    } catch (error) {
      setMessage(`准备新视频失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const jumpTo = (time: number, metadataOverride?: VideoMetadata | null) => {
    seekVideoTo(time, metadataOverride, stage === "target");
  };

  const clearDownstreamResults = () => {
    setSelectedRecordId(null);
    setCurrentCrossing(null);
    setInversion(null);
  };

  const setSelectionFrameTime = (
    time: number,
    options: { boundaryOverride?: NormalBoundary; metadataOverride?: VideoMetadata | null; clearDownstream?: boolean } = {}
  ) => {
    const clampedTime = clampSelectionTime(time, options.boundaryOverride ?? boundary, options.metadataOverride ?? metadata);
    setSelectionTime(clampedTime);
    if (options.clearDownstream !== false) {
      clearDownstreamResults();
    }
    seekVideoTo(clampedTime, options.metadataOverride ?? metadata, true);
  };

  const playerJumpTo = (time: number) => {
    if (stage === "target") {
      setSelectionFrameTime(time);
    } else {
      jumpTo(time);
    }
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    if (stage === "target") {
      setSelectionFrameTime(video.currentTime || selectionTime, { clearDownstream: false });
      setMessage("框选时刻已锁定，请用时间按钮或进度条微调。");
      return;
    }
    if (video.paused) {
      void video.play();
    } else {
      video.pause();
    }
  };

  const adjustBoundary = (field: "zero_v_start_s" | "zero_v_end_s", delta: number) => {
    setBoundaryEdited(true);
    setBoundary((current) => {
      const adjusted = clampBoundary({ ...current, [field]: Number((current[field] + delta).toFixed(3)) }, metadata);
      jumpTo(adjusted[field]);
      return adjusted;
    });
  };

  const adjustSelectionTime = (delta: number) => {
    setSelectionFrameTime(Number((selectionTime + delta).toFixed(3)));
  };

  const restoreMeasurementContext = async (record: NormalRecord, restoredSession: NormalSession | null | undefined, destination: MeasurementStage, markRetry: boolean): Promise<boolean> => {
    let contextSession = restoredSession ?? undefined;
    if (markRetry && !contextSession) {
      setBusy(true);
      try {
        const response = await desktopApi.normalStartNextDroplet({
          session_root: session?.session_root,
          record_id: record.record_id,
          mode: "same_video"
        });
        contextSession = response.session;
        setSession(response.session);
      } catch (error) {
        setMessage(`恢复测量记录失败：${error instanceof Error ? error.message : String(error)}`);
        return false;
      } finally {
        setBusy(false);
      }
    }

    // 旧记录恢复时先看 active_video，缺失的字段才退回 record 自身。
  const activeVideo = (contextSession?.active_video ?? null) as Record<string, any> | null;
    const restoredAdjustment = (activeVideo?.adjustment as Record<string, any> | undefined) ?? {};
    const recordBoundary = record.time_window as NormalBoundary | undefined;
    const activeBoundary = activeVideo?.boundary as NormalBoundary | undefined;
    const nextBoundary = activeBoundary ?? recordBoundary ?? boundary;
    const nextMetadata = (activeVideo?.metadata as VideoMetadata | undefined) ?? (record.metadata as VideoMetadata | undefined) ?? metadata;
    const nextGrid = (activeVideo?.grid as NormalGrid | undefined) ?? (record.grid as NormalGrid | undefined) ?? grid;
    const target = (restoredAdjustment.target ?? record.target) as { target_time_s?: number; source_video_box?: VideoBox } | undefined;
    const overrides = (restoredAdjustment.parameter_overrides ?? record.parameter_overrides) as Record<string, unknown> | undefined;
    const nextVideoPath = typeof activeVideo?.path === "string" ? activeVideo.path : record.video_path ?? videoPath;
    const nextVideoUrl = typeof activeVideo?.video_url === "string" ? activeVideo.video_url : "";

    if (nextMetadata) {
      setMetadata(nextMetadata);
      setDuration(nextMetadata.duration_s || 0);
    }
    if (nextVideoPath) {
      setVideoPath(nextVideoPath);
    }
    setVideoUrl(nextVideoUrl);
    if (nextGrid) {
      setGrid(nextGrid);
    }
    setBoundary(nextBoundary);
    setBoundaryEdited(false);

    const restoredSelectionTime = clampSelectionTime(Number(target?.target_time_s ?? nextBoundary.zero_v_start_s ?? 0), nextBoundary, nextMetadata ?? metadata);
    const restoredVoltage = restoredAdjustment.balance_voltage_V ?? record.balance_voltage_V;
    setSelectionTime(restoredSelectionTime);
    setSelectionBox(target?.source_video_box ?? null);
    setBalanceVoltage(restoredVoltage ? String(restoredVoltage) : "");
    setBalanceConfirmed(Boolean(restoredAdjustment.balance_confirmed ?? record.balance_confirmed ?? record.balance_voltage_V));
    setOverrideFields(flattenOverrideFields(overrides ?? {}));
    setRetrySourceRecordId(markRetry ? String(restoredAdjustment.record_id ?? record.record_id) : null);
    setCurrentCrossing(null);
    setStage(destination);
    seekVideoTo(destination === "boundary" ? Number(nextBoundary.zero_v_start_s ?? restoredSelectionTime) : restoredSelectionTime, nextMetadata ?? metadata, destination === "target");
    return true;
  };

  const reopenRecordForRetry = (record: NormalRecord, restoredSession?: NormalSession | null) => {
    return restoreMeasurementContext(record, restoredSession, "boundary", true);
  };

  const readOverlayGeometry = () => {
    const video = videoRef.current;
    const overlay = overlayRef.current;
    if (!video || !overlay || !metadata) return null;
    const videoRect = video.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    return {
      overlayRect,
      metrics: getContainedVideoMetrics({
        videoRect,
        overlayRect,
        sourceWidth: video.videoWidth || metadata.width || videoRect.width,
        sourceHeight: video.videoHeight || metadata.height || videoRect.height
      })
    };
  };

  const clientToVideoPoint = (event: MouseEvent<HTMLDivElement>, options: { clamp?: boolean } = {}): VideoPoint | null => {
    const geometry = readOverlayGeometry();
    if (!geometry) return null;
    return clientPointToVideoPoint(event.clientX, event.clientY, geometry.overlayRect, geometry.metrics, options);
  };

  const videoBoxStyle = (box: VideoBox) => {
    const geometry = readOverlayGeometry();
    return geometry ? videoBoxToOverlayStyle(box, geometry.metrics) : {};
  };

  const onSelectionDown = (event: MouseEvent<HTMLDivElement>) => {
    if (stage !== "target") return;
    const point = clientToVideoPoint(event);
    if (!point) return;
    setSelectedRecordId(null);
    setCurrentCrossing(null);
    setInversion(null);
    setSelectionAnchor(point);
    setBalanceConfirmed(false);
    setSelectionBox({ x: point.x, y: point.y, width: 1, height: 1 });
  };

  const onSelectionMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!selectionAnchor || stage !== "target") return;
    const point = clientToVideoPoint(event, { clamp: true });
    if (!point) return;
    setSelectionBox({
      x: Math.min(selectionAnchor.x, point.x),
      y: Math.min(selectionAnchor.y, point.y),
      width: Math.max(1, Math.abs(point.x - selectionAnchor.x)),
      height: Math.max(1, Math.abs(point.y - selectionAnchor.y))
    });
  };

  const endSelection = () => {
    setSelectionAnchor(null);
    if (selectionBox && (selectionBox.width < 4 || selectionBox.height < 4)) {
      setMessage("框选区域太小，请拖出一个包住油滴的矩形。");
    }
  };

  const groupOverrideFields = () => {
    const physics: Record<string, number> = {};
    const gridOverrides: Record<string, number> = {};
    for (const [key, raw] of Object.entries(overrideFields)) {
      const value = Number(raw);
      if (!Number.isFinite(value)) continue;
      if (physicsParameterKeys.includes(key)) {
        physics[key] = value;
      } else if (gridParameterKeys.includes(key)) {
        gridOverrides[key] = value;
      }
    }
    return {
      ...(Object.keys(physics).length ? { physics } : {}),
      ...(Object.keys(gridOverrides).length ? { grid: gridOverrides } : {})
    };
  };

  const parameterFieldValue = (key: string) => {
    if (overrideFields[key] !== undefined) {
      return overrideFields[key];
    }
    const source = physicsParameterKeys.includes(key) ? defaultParameters?.physics : defaultParameters?.grid;
    const value = source?.[key];
    return value === undefined || value === null ? "" : String(value);
  };

  const isRecordAcceptable =
    selectedRecord?.status === "pending_user_confirmation" &&
    Boolean(selectedRecord.q_valid) &&
    (selectedRecord.crossings?.length ? allCrossingsConfirmedSame : true);

  const markBoundaryEdited = (nextBoundary: NormalBoundary) => {
    setBoundaryEdited(true);
    setBoundary(nextBoundary);
    setSelectedRecordId(null);
    setCurrentCrossing(null);
    setInversion(null);
  };

  const backToBoundary = (record?: NormalRecord | null) => {
    if (record) {
      void restoreMeasurementContext(record, undefined, "boundary", true).then((restored) => {
        if (restored) setMessage("已恢复该测量，可调整区间后重新追踪。");
      });
      return;
    }
    setStage("boundary");
    setCurrentCrossing(null);
    setMessage("已返回 确认零电压区间。会在上次确认基础上微调；确认修改后需重新框选并追踪。");
    jumpTo(boundary.zero_v_start_s);
  };

  const backToTarget = (record?: NormalRecord | null) => {
    if (record) {
      void restoreMeasurementContext(record, undefined, "target", true).then((restored) => {
        if (restored) setMessage("已恢复该测量，请调整框选后重新追踪。");
      });
      return;
    }
    setStage("target");
    clearDownstreamResults();
    const clampedTime = clampSelectionTime(selectionTime || boundary.zero_v_start_s, boundary, metadata);
    setSelectionTime(clampedTime);
    setMessage("已返回框选目标。保留已确认边界和参数；修改框选后会重新追踪。");
    seekVideoTo(clampedTime, metadata, true);
  };

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
                      onLoadedMetadata={(event) => {
                        setDuration(event.currentTarget.duration || metadata?.duration_s || 0);
                        const initialTime = stage === "target"
                          ? clampSelectionTime(selectionTime, boundary, metadata)
                          : stage === "boundary"
                            ? Number(boundary.zero_v_start_s || 0)
                            : event.currentTarget.currentTime || 0;
                        if (stage === "target" || stage === "boundary") {
                          event.currentTarget.currentTime = initialTime;
                        }
                        setCurrentTime(initialTime);
                      }}
                      onTimeUpdate={(event) => {
                        const time = event.currentTarget.currentTime || 0;
                        if (stage === "target") {
                          const safe = clampSelectionTime(time, boundary, metadata);
                          if (Math.abs(safe - time) > 0.01) {
                            event.currentTarget.currentTime = safe;
                          }
                          event.currentTarget.pause();
                          setSelectionTime(safe);
                          setCurrentTime(safe);
                        } else {
                          setCurrentTime(time);
                        }
                      }}
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
              onBoundary={markBoundaryEdited}
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
              parameterFieldValue={parameterFieldValue}
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
              isRecordAcceptable={isRecordAcceptable}
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
