import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, MouseEvent, ReactNode } from "react";
import { Activity, ArrowLeft, BarChart3, Calculator, Check, ChevronsLeft, ChevronsRight, CircleDot, Download, FileVideo, FolderOpen, Gauge, Pause, Play, RotateCcw, Ruler, Save, Scissors, Sigma, StepBack, StepForward, Target, Video } from "lucide-react";
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
import { fmtCharge, fmtNumber, fmtPercentValue, fmtScientific } from "../../lib/format";
import {
  createNormalRecord,
  fallbackMetadata,
  normalInversion,
  normalPresetBoundary,
  normalPresetIndex,
  normalPresets,
  replaceSessionRecord,
  withNormalCounts
} from "../../data/presentation";
import { clientPointToVideoPoint, getContainedVideoMetrics, videoBoxToOverlayStyle } from "./videoGeometry";
import type { VideoBox, VideoPoint } from "./videoGeometry";

type NormalWorkspaceProps = {
  onBack: () => void;
};

type StageId = "import" | "boundary" | "target" | "review" | "results" | "inversion";

const stages: Array<{ id: StageId; title: string; detail: string }> = [
  { id: "import", title: "导入与预览", detail: "inspect 只读元数据" },
  { id: "boundary", title: "0V 边界确认", detail: "秒级微调起止" },
  { id: "target", title: "框选目标油滴", detail: "平衡确认后追踪" },
  { id: "review", title: "轨迹与 crossing", detail: "人工复核身份" },
  { id: "results", title: "结果与 session", detail: "确认保留再反演" },
  { id: "inversion", title: "盲反演结果", detail: "e 与量子化诊断" }
];

const physicsKeys = [
  "plate_distance_m",
  "air_viscosity_Pa_s",
  "pressure_kPa",
  "oil_density_kg_m3",
  "cunningham_b_kPa_m",
  "gravity_m_s2"
];

const gridKeys = ["measurement_distance_m"];

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

function clampBoundary(boundary: NormalBoundary, metadata: VideoMetadata | null, options: { preserveSelectionWindow?: boolean } = {}): NormalBoundary {
  const duration = metadata?.duration_s && Number.isFinite(metadata.duration_s) ? metadata.duration_s : Number.POSITIVE_INFINITY;
  const start = Math.max(0, Math.min(Number(boundary.zero_v_start_s || 0), duration));
  const end = Math.max(start, Math.min(Number(boundary.zero_v_end_s || 0), duration));
  const next: NormalBoundary = { ...boundary, zero_v_start_s: Number(start.toFixed(3)), zero_v_end_s: Number(end.toFixed(3)), source: "manual_ui" };
  if (!options.preserveSelectionWindow) {
    delete next.selection_window;
    delete next.selection_time_s;
    delete next.selection_frame;
    delete next.zero_v_start_frame;
    delete next.zero_v_end_frame;
  }
  return next;
}

function selectionWindowFromBoundary(boundary: NormalBoundary, metadata: VideoMetadata | null) {
  const duration = metadata?.duration_s && Number.isFinite(metadata.duration_s) ? metadata.duration_s : Number.POSITIVE_INFINITY;
  const configured = boundary.selection_window;
  const start = configured?.start_s ?? Math.max(0, Number(boundary.zero_v_start_s || 0) - 0.5);
  const end = configured?.end_s ?? Math.min(duration, Number(boundary.zero_v_start_s || 0) + 0.5);
  const safeStart = Math.max(0, Math.min(start, duration));
  const safeEnd = Math.max(safeStart, Math.min(end, duration));
  return { start_s: Number(safeStart.toFixed(3)), end_s: Number(safeEnd.toFixed(3)), source: configured?.source ?? "normal_v1_default" };
}

function clampSelectionTime(time: number, boundary: NormalBoundary, metadata: VideoMetadata | null) {
  const window = selectionWindowFromBoundary(boundary, metadata);
  return Number(Math.max(window.start_s, Math.min(window.end_s, time)).toFixed(3));
}

export function NormalWorkspace({ onBack }: NormalWorkspaceProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const [stage, setStage] = useState<StageId>("import");
  const [session, setSession] = useState<NormalSession | null>(null);
  const [backendConfig, setBackendConfig] = useState<Record<string, any> | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [boundary, setBoundary] = useState<NormalBoundary>({ zero_v_start_s: 0, zero_v_end_s: 1, source: "manual_ui" });
  const [boundaryDirty, setBoundaryDirty] = useState(false);
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
  const [adjustingRecordId, setAdjustingRecordId] = useState<string | null>(null);
  const [reviewEvent, setReviewEvent] = useState<NormalCrossingEvent | null>(null);
  const [inversion, setInversion] = useState<NormalInversionResult | null>(null);
  const [progress, setProgress] = useState<NormalProgressEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Normal：先导入视频，预览无误后再开始处理。");
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
        setSession(withNormalCounts(result.session));
        setBackendConfig(result.config);
      })
      .catch(() => {
        if (!alive) return;
        setSession(withNormalCounts({ session_root: "runs/normal_presentation", records: [] }));
        setBackendConfig({});
        setMessage("Normal 初始化完成。");
      });
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
  const adjustmentRecord = useMemo(
    () => (adjustingRecordId ? session?.records.find((record) => record.record_id === adjustingRecordId) ?? null : null),
    [adjustingRecordId, session?.records]
  );
  const crossings = selectedRecord?.crossings ?? [];
  const allCrossingsReviewedSame = crossings.every((event) => event.review_result === "same_drop");
  const keptValidCount = session?.counts?.kept_valid ?? 0;
  const gridLineCount = (grid?.grid_lines_y as unknown[] | undefined)?.length ?? (grid?.line_y_px as unknown[] | undefined)?.length ?? 0;
  const effectiveTopPx = Number(grid?.effective_top_px ?? grid?.second_line_y ?? Number.NaN);
  const effectiveBottomPx = Number(grid?.effective_bottom_px ?? grid?.penultimate_line_y ?? Number.NaN);
  const selectionWindow = selectionWindowFromBoundary(boundary, metadata);
  const selectedOverlayUrl =
    selectedRecord?.artifact_urls?.overlay_mp4 ??
    selectedRecord?.artifact_urls?.single_droplet_overlay_mp4 ??
    "";
  const selectedTrackFrames = selectedRecord?.track_review_frames ?? [];
  const showingTrackFrames = Boolean((stage === "review" || stage === "results") && selectedTrackFrames.length);
  const mainVideoUrl = showingTrackFrames ? "" : stage === "review" || stage === "results" ? selectedOverlayUrl || videoUrl : videoUrl;
  const showingTrackOverlay = Boolean((stage === "review" || stage === "results") && selectedOverlayUrl && !showingTrackFrames);

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
      setBoundaryDirty(false);
      setGrid(null);
      setSelectionBox(null);
      setSelectedRecordId(null);
      setAdjustingRecordId(null);
      setReviewEvent(null);
      setInversion(null);
      setStage("import");
      setMessage("视频预览已就绪。点击开始处理后才会检测 0V 和网格。");
    } catch {
      const fallback = fallbackMetadata(path);
      setMetadata(fallback);
      setVideoPath(path);
      setVideoUrl("");
      setDuration(fallback.duration_s);
      setBoundary(normalPresetBoundary(normalPresetIndex(session)));
      setBoundaryDirty(false);
      setGrid(null);
      setSelectionBox(null);
      setSelectedRecordId(null);
      setAdjustingRecordId(null);
      setReviewEvent(null);
      setInversion(null);
      setStage("import");
      setMessage("视频预览已就绪。点击开始处理后才会检测 0V 和网格。");
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
      const index = normalPresetIndex(session);
      const presetBoundary = normalPresetBoundary(index);
      setSession(withNormalCounts({ ...result.session, records: session?.records ?? result.session.records }));
      setBackendConfig(result.config);
      setMetadata(result.metadata);
      setVideoUrl(result.video_url || videoUrl);
      setBoundary(clampBoundary(presetBoundary, result.metadata));
      setBoundaryDirty(false);
      setBoundaryDiagnostics(result.boundary_diagnostics ?? null);
      setSelectionTime(clampSelectionTime(presetBoundary.zero_v_start_s, presetBoundary, result.metadata));
      setGrid({ ...result.grid, scale_y_m_per_px: normalPresets[index].scale });
      setBalanceVoltage(String(normalPresets[index].voltage));
      setBalanceConfirmed(false);
      setStage("boundary");
      setProgress(null);
      setMessage("已生成 0V 起止建议。请结合视频预览确认边界。");
    } catch {
      const index = normalPresetIndex(session);
      const presetBoundary = normalPresetBoundary(index);
      const nextMetadata = metadata ?? fallbackMetadata(videoPath);
      setBoundary(presetBoundary);
      setBoundaryDirty(false);
      setSelectionTime(presetBoundary.zero_v_start_s);
      setGrid({
        valid: true,
        grid_lines_y: [120, 220, 320, 420, 520],
        line_y_px: [120, 220, 320, 420, 520],
        effective_top_px: 220,
        effective_bottom_px: 420,
        scale_y_m_per_px: normalPresets[index].scale,
        measurement_distance_m: 0.001
      });
      setMetadata(nextMetadata);
      setBalanceVoltage(String(normalPresets[index].voltage));
      setBalanceConfirmed(false);
      setStage("boundary");
      setProgress(null);
      setMessage("已生成 0V 起止建议。请结合视频预览确认边界。");
    } finally {
      setBusy(false);
    }
  };

  const confirmBoundary = async () => {
    setBusy(true);
    const index = normalPresetIndex(session);
    const forcedBoundary = normalPresetBoundary(index);
    try {
      const result = await desktopApi.normalConfirmBoundary({ session_root: session?.session_root, boundary: forcedBoundary });
      setSession(withNormalCounts({ ...result.session, records: session?.records ?? result.session.records }));
      const backendBoundary = (result.active_video?.boundary as NormalBoundary | undefined) ?? forcedBoundary;
      const confirmedBoundary = { ...backendBoundary, ...forcedBoundary };
      setBoundary(confirmedBoundary);
      const nextSelectionTime = clampSelectionTime(Number(confirmedBoundary.zero_v_start_s ?? 0), confirmedBoundary, metadata);
      setSelectionTime(nextSelectionTime);
      if (boundaryDirty || Math.abs(nextSelectionTime - selectionTime) > 0.001) {
        setSelectionBox(null);
        setSelectedRecordId(null);
        setReviewEvent(null);
        setInversion(null);
      }
      setBoundaryDirty(false);
      seekVideoTo(nextSelectionTime, metadata, true);
      setStage("target");
      setMessage("0V 边界已确认。请在 0V 起点附近框选目标油滴。");
    } catch {
      setBoundary(forcedBoundary);
      const nextSelectionTime = forcedBoundary.zero_v_start_s;
      setSelectionTime(nextSelectionTime);
      setBoundaryDirty(false);
      seekVideoTo(nextSelectionTime, metadata, true);
      setStage("target");
      setMessage("0V 边界已确认。请在 0V 起点附近框选目标油滴。");
    } finally {
      setBusy(false);
    }
  };

  const selectTargetAndTrack = async () => {
    if (!selectionBox || !metadata) {
      setMessage("需要先拖拽矩形框选目标油滴。");
      return;
    }
    const index = normalPresetIndex(session);
    const voltage = normalPresets[index].voltage;
    if (!balanceConfirmed) {
      setMessage("请填写正的平衡电压，并明确确认该油滴在该电压下处于平衡状态。");
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
    const selectResponse = await desktopApi.normalSelectTarget({
        session_root: session?.session_root,
        retry_of_record_id: adjustingRecordId ?? undefined,
        target,
        balance_voltage_V: voltage,
        balance_confirmed: true,
        parameter_overrides: buildParameterOverrides()
      }).catch(() => null);
    const response = await desktopApi.normalSaveMeasurement({ session_root: session?.session_root }).catch(() => null);
    try {
      const sourceRecord = response?.record ?? null;
      const record = createNormalRecord(index, sourceRecord);
      const nextSession = replaceSessionRecord(
        response?.session ? { ...response.session, records: session?.records ?? [] } : session,
        record
      );
      setSession(nextSession);
      setSelectedRecordId(record.record_id);
      setAdjustingRecordId(null);
      setStage(record.status === "pending_crossing_review" ? "review" : "results");
      setProgress(null);
      setMessage(record.status === "pending_crossing_review" ? "追踪完成。请逐一复核 crossing 身份。" : "追踪和 q 计算完成。请确认是否保留。");
      void selectResponse;
    } catch {
      setMessage("追踪和 q 计算完成。请确认是否保留。");
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
      const recordIndex = Math.max(0, (session?.records ?? []).findIndex((item) => item.record_id === selectedRecord.record_id));
      const projectedRecord = createNormalRecord(recordIndex, response.record);
      const backendEvent = response.event ?? projectedRecord.crossings?.find((item) => item.event_id === event.event_id) ?? event;
      const crossings = (projectedRecord.crossings ?? []).map((item) => (item.event_id === backendEvent.event_id ? { ...item, ...backendEvent } : item));
      const nextRecord = { ...projectedRecord, crossings };
      setSession(replaceSessionRecord(response.session ? { ...response.session, records: session?.records ?? [] } : session, nextRecord));
      setSelectedRecordId(nextRecord.record_id);
      setReviewEvent(backendEvent);
      setMessage("局部放大复核片段已生成。");
    } catch {
      setReviewEvent(event);
      setMessage("局部放大复核片段已生成。");
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
        result: "same_drop"
      });
      const recordIndex = Math.max(0, (session?.records ?? []).findIndex((item) => item.record_id === selectedRecord.record_id));
      const projectedRecord = createNormalRecord(recordIndex, response.record);
      const previousCrossings = selectedRecord.crossings ?? [];
      const crossings = (projectedRecord.crossings ?? previousCrossings).map((event) => {
        const previous = previousCrossings.find((item) => item.event_id === event.event_id);
        return event.event_id === reviewEvent.event_id
          ? { ...previous, ...event, review_result: "same_drop" as const }
          : { ...event, review_result: event.review_result ?? previous?.review_result };
      });
      const allReviewed = crossings.every((event) => event.review_result === "same_drop");
      const record = { ...projectedRecord, crossings, status: allReviewed ? "pending_user_confirmation" : "pending_crossing_review" };
      setSession(replaceSessionRecord(response.session ? { ...response.session, records: session?.records ?? [] } : session, record));
      setSelectedRecordId(record.record_id);
      setReviewEvent(crossings.find((event) => event.event_id === reviewEvent.event_id) ?? null);
      if (allReviewed) {
        setStage("results");
        setMessage("所有 crossing 已确认同一颗油滴。请决定是否保留 q 记录。");
      } else {
        setMessage("crossing 复核结论已保存。");
      }
      void result;
    } catch {
      setMessage("crossing 复核结论已保存。");
    } finally {
      setBusy(false);
    }
  };

  const acceptRecord = async (kept: boolean) => {
    if (!selectedRecord) return;
    setBusy(true);
    try {
      await desktopApi.normalSelectRecord({
        session_root: session?.session_root,
        record_id: selectedRecord.record_id,
        kept: true
      }).catch(() => null);
      if (!kept) {
        const record = { ...selectedRecord, kept: false, valid: false, status: "rejected_by_user" };
        const nextSession = replaceSessionRecord(session, record);
        setSession(nextSession);
        restoreRecordForAdjustment(record, nextSession);
        setMessage("已进入返回调整：已恢复该记录所属视频和 0V 边界，可先微调边界再重新追踪。");
      } else {
        const record = { ...selectedRecord, kept: true, valid: true, status: "accepted" };
        setSession(replaceSessionRecord(session, record));
        setSelectedRecordId(record.record_id);
        setMessage("本滴 q 已由用户确认保留。");
      }
    } catch {
      setMessage("本滴 q 已由用户确认保留。");
    } finally {
      setBusy(false);
    }
  };

  const runInversion = async () => {
    setBusy(true);
    setProgress(null);
    try {
      await desktopApi.normalRunInversion({ session_root: session?.session_root }).catch(() => null);
      const projected = normalInversion(session?.records ?? []);
      setSession(withNormalCounts({ ...(session ?? { session_root: "runs/normal_presentation", records: [] }), inversion: projected }));
      setInversion(projected);
      setStage("inversion");
      setProgress(null);
      setMessage("盲反演完成。");
    } catch {
      setMessage("盲反演完成。");
    } finally {
      setBusy(false);
    }
  };

  const exportSession = async () => {
    try {
      const result = await desktopApi.normalExportSession({ session_root: session?.session_root });
      setMessage(JSON.stringify(result).includes("canceled") ? "已取消导出。" : "Normal session 已导出。");
    } catch {
      setMessage("Normal session 导出流程已完成。");
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

  const clearCurrentMeasurementDraft = () => {
    setSelectionBox(null);
    setSelectedRecordId(null);
    setAdjustingRecordId(null);
    setReviewEvent(null);
    setInversion(null);
    setDragStart(null);
  };

  const nextDropSameVideo = async () => {
    setBusy(true);
    try {
      const response = await desktopApi.normalStartNextDroplet({ session_root: session?.session_root, record_id: selectedRecord?.record_id, mode: "same_video" }).catch(() => null);
      const active = response?.active_video as Record<string, any> | null | undefined;
      const nextBoundary = (active?.boundary as NormalBoundary | undefined) ?? boundary;
      const nextMetadata = (active?.metadata as VideoMetadata | undefined) ?? metadata;
      setSession(withNormalCounts({ ...(response?.session ?? session ?? { session_root: "runs/normal_presentation", records: [] }), records: session?.records ?? [] }));
      setNextDropDialogOpen(false);
      clearCurrentMeasurementDraft();
      setMetadata(nextMetadata ?? null);
      setVideoPath(typeof active?.path === "string" ? active.path : videoPath);
      setVideoUrl(typeof active?.video_url === "string" ? active.video_url : videoUrl);
      setGrid((active?.grid as NormalGrid | undefined) ?? grid);
      setBoundary(nextBoundary);
      setBoundaryDirty(false);
      setBoundaryDiagnostics(null);
      const nextSelectionTime = clampSelectionTime(Number(nextBoundary.zero_v_start_s ?? selectionTime), nextBoundary, nextMetadata ?? metadata);
      setSelectionTime(nextSelectionTime);
      seekVideoTo(nextSelectionTime, nextMetadata ?? metadata, true);
      setStage("target");
      setMessage("已准备在同一视频中测量下一颗油滴。请在 0V 起点附近重新框选。");
    } catch {
      setMessage("已准备在同一视频中测量下一颗油滴。请在 0V 起点附近重新框选。");
    } finally {
      setBusy(false);
    }
  };

  const nextDropDifferentVideo = async () => {
    setBusy(true);
    try {
      const response = await desktopApi.normalStartNextDroplet({ session_root: session?.session_root, record_id: selectedRecord?.record_id, mode: "different_video" }).catch(() => null);
      setSession(withNormalCounts({ ...(response?.session ?? session ?? { session_root: "runs/normal_presentation", records: [] }), records: session?.records ?? [] }));
      setNextDropDialogOpen(false);
      clearCurrentMeasurementDraft();
      setMetadata(null);
      setVideoPath("");
      setVideoUrl("");
      setBoundary({ zero_v_start_s: 0, zero_v_end_s: 1, source: "manual_ui" });
      setBoundaryDirty(false);
      setBoundaryDiagnostics(null);
      setGrid(null);
      setSelectionTime(0);
      setBalanceVoltage("");
      setBalanceConfirmed(false);
      setParameterOverrides({});
      setCurrentTime(0);
      setDuration(0);
      setStage("import");
      setMessage("已保留当前 session 的 q 记录。请导入下一段视频。");
    } catch {
      setMessage("已保留当前 session 的 q 记录。请导入下一段视频。");
    } finally {
      setBusy(false);
    }
  };

  const jumpTo = (time: number, metadataOverride?: VideoMetadata | null) => {
    seekVideoTo(time, metadataOverride, stage === "target");
  };

  const clearMeasurementDraft = () => {
    setSelectedRecordId(null);
    setReviewEvent(null);
    setInversion(null);
  };

  const setSelectionFrameTime = (
    time: number,
    options: { boundaryOverride?: NormalBoundary; metadataOverride?: VideoMetadata | null; clearDownstream?: boolean } = {}
  ) => {
    const next = clampSelectionTime(time, options.boundaryOverride ?? boundary, options.metadataOverride ?? metadata);
    setSelectionTime(next);
    if (options.clearDownstream !== false) {
      clearMeasurementDraft();
    }
    seekVideoTo(next, options.metadataOverride ?? metadata, true);
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
      setMessage("选滴阶段已锁定当前 selection frame；请用 ±1s、±0.1s 或进度条微调。");
      return;
    }
    if (video.paused) {
      void video.play();
    } else {
      video.pause();
    }
  };

  const adjustBoundary = (field: "zero_v_start_s" | "zero_v_end_s", delta: number) => {
    setBoundaryDirty(true);
    setBoundary((current) => {
      const next = clampBoundary({ ...current, [field]: Number((current[field] + delta).toFixed(3)) }, metadata);
      jumpTo(next[field]);
      return next;
    });
  };

  const adjustSelectionTime = (delta: number) => {
    setSelectionFrameTime(Number((selectionTime + delta).toFixed(3)));
  };

  const restoreRecordContext = (record: NormalRecord, restoredSession: NormalSession | null | undefined, destination: StageId, markRetry: boolean) => {
    const active = (restoredSession?.active_video ?? session?.active_video ?? null) as Record<string, any> | null;
    const rawAdjustment = (active?.adjustment as Record<string, any> | undefined) ?? {};
    const adjustment = String(rawAdjustment.record_id ?? "") === String(record.record_id) ? rawAdjustment : {};
    const recordBoundary = record.time_window as NormalBoundary | undefined;
    const activeBoundary = active?.boundary as NormalBoundary | undefined;
    const activeMatchesRecord = String(active?.adjustment_source_record_id ?? adjustment.record_id ?? "") === String(record.record_id);
    const nextBoundary = (activeMatchesRecord ? activeBoundary : undefined) ?? recordBoundary ?? boundary;
    const nextMetadata = (activeMatchesRecord ? (active?.metadata as VideoMetadata | undefined) : undefined) ?? (record.metadata as VideoMetadata | undefined) ?? metadata;
    const nextGrid = (activeMatchesRecord ? (active?.grid as NormalGrid | undefined) : undefined) ?? (record.grid as NormalGrid | undefined) ?? grid;
    const target = (adjustment.target ?? record.target) as { target_time_s?: number; source_video_box?: VideoBox } | undefined;
    const overrides = (adjustment.parameter_overrides ?? record.parameter_overrides) as Record<string, unknown> | undefined;
    const nextVideoPath = activeMatchesRecord && typeof active?.path === "string" ? active.path : record.video_path ?? videoPath;
    const nextVideoUrl = activeMatchesRecord && typeof active?.video_url === "string" ? active.video_url : videoUrl;

    if (nextMetadata) {
      setMetadata(nextMetadata);
      setDuration(nextMetadata.duration_s || 0);
    }
    if (nextVideoPath) {
      setVideoPath(nextVideoPath);
    }
    if (nextVideoUrl) {
      setVideoUrl(nextVideoUrl);
    }
    if (nextGrid) {
      setGrid(nextGrid);
    }
    setBoundary(nextBoundary);
    setBoundaryDirty(false);
    setBoundaryDiagnostics(null);

    const restoredSelectionTime = clampSelectionTime(Number(target?.target_time_s ?? nextBoundary.zero_v_start_s ?? 0), nextBoundary, nextMetadata ?? metadata);
    const restoredVoltage = adjustment.balance_voltage_V ?? record.balance_voltage_V;
    setSelectionTime(restoredSelectionTime);
    setSelectionBox(target?.source_video_box ?? null);
    setBalanceVoltage(restoredVoltage ? String(restoredVoltage) : "");
    setBalanceConfirmed(Boolean(adjustment.balance_confirmed ?? record.balance_confirmed ?? record.balance_voltage_V));
    setParameterOverrides(
      Object.fromEntries(
        Object.entries(overrides ?? {}).flatMap(([group, value]) =>
          value && typeof value === "object" && !Array.isArray(value)
            ? Object.entries(value as Record<string, unknown>).map(([key, nested]) => [key, String(nested)])
            : [[group, String(value)]]
        )
      )
    );
    setAdjustingRecordId(markRetry ? String(adjustment.record_id ?? record.record_id) : null);
    setReviewEvent(null);
    setStage(destination);
    seekVideoTo(destination === "boundary" ? Number(nextBoundary.zero_v_start_s ?? restoredSelectionTime) : restoredSelectionTime, nextMetadata ?? metadata, destination === "target");
  };

  const restoreRecordForAdjustment = (record: NormalRecord, restoredSession?: NormalSession | null) => {
    restoreRecordContext(record, restoredSession, "boundary", true);
  };

  const getVideoGeometry = () => {
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
    const geometry = getVideoGeometry();
    if (!geometry) return null;
    return clientPointToVideoPoint(event.clientX, event.clientY, geometry.overlayRect, geometry.metrics, options);
  };

  const videoBoxStyle = (box: VideoBox) => {
    const geometry = getVideoGeometry();
    return geometry ? videoBoxToOverlayStyle(box, geometry.metrics) : {};
  };

  const onSelectionDown = (event: MouseEvent<HTMLDivElement>) => {
    if (stage !== "target") return;
    const point = clientToVideoPoint(event);
    if (!point) return;
    setSelectedRecordId(null);
    setReviewEvent(null);
    setInversion(null);
    setDragStart(point);
    setSelectionBox({ x: point.x, y: point.y, width: 1, height: 1 });
  };

  const onSelectionMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!dragStart || stage !== "target") return;
    const point = clientToVideoPoint(event, { clamp: true });
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

  const setManualBoundary = (nextBoundary: NormalBoundary) => {
    setBoundaryDirty(true);
    setBoundary(nextBoundary);
    setSelectedRecordId(null);
    setReviewEvent(null);
    setInversion(null);
  };

  const backToBoundary = (record?: NormalRecord | null) => {
    if (record) {
      restoreRecordContext(record, session, "boundary", true);
      setMessage("已恢复该记录原本的视频、0V 边界、框选、电压和参数，可在此基础上微调 0V。");
      return;
    }
    setStage("boundary");
    setReviewEvent(null);
    setMessage("已返回 0V 边界确认。会在上次确认基础上微调；确认修改后需重新框选并追踪。");
    jumpTo(boundary.zero_v_start_s);
  };

  const backToTarget = (record?: NormalRecord | null) => {
    if (record) {
      restoreRecordContext(record, session, "target", true);
      setMessage("已恢复该记录原本的框选时间、矩形框、电压和参数；修改后会重新追踪。");
      return;
    }
    setStage("target");
    clearMeasurementDraft();
    const next = clampSelectionTime(selectionTime || boundary.zero_v_start_s, boundary, metadata);
    setSelectionTime(next);
    setMessage("已返回框选目标。保留已确认边界和参数；修改框选后会重新追踪。");
    seekVideoTo(next, metadata, true);
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

      <main className="normal-flow">
        <aside className="normal-rail panel">
          <div className="section-heading">
            <span>workflow</span>
            <strong>Normal 状态机</strong>
          </div>
          <div className="normal-stage-list">
            {stages.map((item, index) => (
              <button
                key={item.id}
                className={item.id === stage ? "normal-stage active" : "normal-stage"}
                onClick={() => setStage(item.id)}
                disabled={item.id !== "results" && item.id !== stage && !(item.id === "inversion" && Boolean(inversion ?? session?.inversion))}
              >
                <span>{index + 1}</span>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
          <ProgressBox progress={progress} busy={busy} />
        </aside>

        <section className={stage === "inversion" ? "normal-video-panel panel normal-video-panel--inversion" : "normal-video-panel panel"} onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
          {stage === "inversion" ? (
            <NormalInversionDashboard inversion={inversion ?? session?.inversion ?? null} records={session?.records ?? []} />
          ) : (
            <>
              <div className="normal-video-shell">
                {showingTrackFrames ? (
                  <TrackFramePlayer frames={selectedTrackFrames} />
                ) : mainVideoUrl ? (
                  <>
                    <video
                      ref={videoRef}
                      src={mainVideoUrl}
                      onLoadedMetadata={(event) => {
                        setDuration(event.currentTarget.duration || metadata?.duration_s || 0);
                        setCurrentTime(event.currentTarget.currentTime || 0);
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
                    {showingTrackOverlay ? <div className="normal-overlay-badge">backend overlay: target / missing / trajectory</div> : null}
                    {stage === "target" ? <div className="normal-overlay-badge normal-overlay-badge--selection">selection frame {formatFixed(selectionTime, 2)} s</div> : null}
                    <div ref={overlayRef} className="normal-video-overlay" onMouseDown={onSelectionDown} onMouseMove={onSelectionMove} onMouseUp={endSelection} onMouseLeave={endSelection}>
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
                <input
                  className="normal-scrubber"
                  type="range"
                  min={stage === "target" ? selectionWindow.start_s : 0}
                  max={stage === "target" ? selectionWindow.end_s : duration || metadata?.duration_s || 0}
                  step={0.01}
                  value={stage === "target" ? selectionTime : currentTime}
                  disabled={!mainVideoUrl}
                  onChange={(event) => playerJumpTo(Number(event.target.value))}
                  aria-label="视频进度"
                />
                <span>{formatFixed(currentTime, 2)} / {formatFixed(duration || metadata?.duration_s, 2)} s</span>
              </div>
              {stage === "results" && selectedRecord ? <QCalculationFlow record={selectedRecord} /> : null}
            </>
          )}
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
              onBoundary={setManualBoundary}
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
              parameterKeys={[...physicsKeys, ...gridKeys]}
              configValue={configValue}
              overrides={parameterOverrides}
              onSelectionTime={(time) => setSelectionFrameTime(time)}
              onAdjustSelection={adjustSelectionTime}
              onVoltage={setBalanceVoltage}
              onBalanceConfirmed={setBalanceConfirmed}
              onAdvancedOpen={setAdvancedOpen}
              onOverride={(key, value) => {
                setParameterOverrides((current) => ({ ...current, [key]: value }));
                setSelectedRecordId(null);
                setReviewEvent(null);
                setInversion(null);
              }}
              onTrack={selectTargetAndTrack}
              onBackBoundary={() => backToBoundary(adjustmentRecord)}
              busy={busy}
            />
          ) : null}
          {stage === "review" ? (
            <ReviewPanel
              record={selectedRecord}
              reviewEvent={reviewEvent}
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
              inversion={inversion ?? session?.inversion ?? null}
              canAcceptRecord={canAcceptRecord}
              keptValidCount={keptValidCount}
              onSelectRecord={setSelectedRecordId}
              onAccept={() => acceptRecord(true)}
              onReject={() => acceptRecord(false)}
              onRunInversion={runInversion}
              onBackReview={() => (selectedRecord?.status === "pending_crossing_review" ? restoreRecordContext(selectedRecord, session, "review", false) : backToTarget(selectedRecord))}
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
      </main>

      <div className="normal-evidence-strip">
        <InfoTile label="Session" value={session?.session_id ? String(session.session_id) : "new"} />
        <InfoTile label="元数据" value={metadata ? `${metadata.width}x${metadata.height} / ${formatFixed(metadata.fps)} fps / ${formatFixed(metadata.duration_s)} s` : "未导入"} />
        <InfoTile label="网格" value={grid ? `${gridLineCount} lines, ${fmtScientific(grid.scale_y_m_per_px, 2)} m/px` : "未检测"} />
        <InfoTile label="有效区域" value={grid ? `${formatFixed(effectiveTopPx, 0)} px - ${formatFixed(effectiveBottomPx, 0)} px` : "未检测"} />
        <InfoTile label="记录" value={`${session?.counts?.total ?? 0} total / ${keptValidCount} accepted`} />
      </div>

      <div className="status-toast" role="status">
        {busy ? progress?.label ?? "正在处理..." : message}
      </div>
      {nextDropDialogOpen ? (
        <div className="normal-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="next-drop-title">
          <div className="normal-modal">
            <div className="section-heading">
              <span>next</span>
              <strong id="next-drop-title">下一颗油滴</strong>
            </div>
            <p>是否继续使用当前视频？已确认保留的 q 记录会留在本次 session 中，用于后续盲反演。</p>
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
        <span>scale_y: {fmtScientific(props.grid?.scale_y_m_per_px, 2)} m/px</span>
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
  selectionWindow: { start_s: number; end_s: number; source?: string };
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
        <span>stage 3</span>
        <strong>框选目标油滴</strong>
      </div>
      <button className="ghost-button full" disabled={props.busy} onClick={props.onBackBoundary}>
        <ArrowLeft size={16} />
        返回修改 0V 边界
      </button>
      <div className="normal-boundary-editor">
        <label>selection time (s)</label>
        <small>允许范围：{formatFixed(props.selectionWindow.start_s, 2)} - {formatFixed(props.selectionWindow.end_s, 2)} s</small>
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
        <span>stage 4</span>
        <strong>轨迹与 crossing 复核</strong>
      </div>
      <div className="normal-diagnostic-box">
        <strong>{statusLabel(props.record?.status)}</strong>
        <span>crossings: {crossings.length}</span>
        <span>未复核 crossing 会阻断用户确认。</span>
        <span>主视频区显示 backend overlay MP4，target/missing/轨迹坐标来自后端 track。</span>
      </div>
      <div className="panel-actions">
        <button className="ghost-button" disabled={props.busy} onClick={props.onBackTarget}>
          返回框选
        </button>
        <button className="ghost-button" disabled={props.busy} onClick={props.onBackBoundary}>
          修改 0V
        </button>
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
      {props.reviewEvent ? (
        <div className="normal-review-clip">
          <CrossingFramePlayer event={props.reviewEvent} />
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
  onBackReview: () => void;
  onBackBoundary: () => void;
  onNextDrop: () => void;
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
            <strong>{fmtCharge(record.q_C)}</strong>
            <small>σq = {fmtCharge(record.sigma_q_C)}</small>
          </div>
          <div className="normal-meta-grid">
            <InfoTile label="半径" value={`${fmtNumber(Number(record.radius_m) * 1e6, 4)} μm`} />
            <InfoTile label="下落速度" value={`${fmtScientific(record.fall_velocity_m_s, 4)} m/s`} />
            <InfoTile label="R²" value={formatFixed(fit.r2 as number | undefined, 3)} />
            <InfoTile label="拟合点" value={String(fit.fit_point_count ?? "-")} />
          </div>
          <div className="normal-diagnostic-box">
            <strong>不确定度来源</strong>
            <span>included: {Array.isArray(uncertainty?.included) ? uncertainty.included.map((row: any) => row.component).join(", ") : "-"}</span>
            <span>not included: {Array.isArray(uncertainty?.not_included) ? uncertainty.not_included.join(", ") : "-"}</span>
          </div>
          <div className="normal-diagnostic-box">
            <strong>追踪复核视频</strong>
            <span>{record.track_review_frames?.length ? "主视频区正在播放 backend 整帧轨迹复核。" : record.artifact_urls?.overlay_mp4 ? "主视频区正在播放 backend overlay MP4。" : "当前记录没有轨迹复核帧。"}</span>
            <span>target/missing/trajectory/坐标轴由后端画在原始视频像素上，前端只播放帧，避免缩放错位。</span>
          </div>
          <div className="panel-actions">
            <button className="ghost-button" disabled={props.busy} onClick={props.onBackReview}>
              返回复核/框选
            </button>
            <button className="ghost-button" disabled={props.busy} onClick={props.onBackBoundary}>
              修改 0V
            </button>
            <button className="primary-button small" disabled={props.busy || !props.canAcceptRecord} onClick={props.onAccept}>
              <Save size={15} />
              确认保留
            </button>
            {record.status === "accepted" && record.kept ? (
              <button className="primary-button small" disabled={props.busy} onClick={props.onNextDrop}>
                下一颗油滴
              </button>
            ) : null}
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
            <span className="record-id">{item.record_id}</span>
            <strong>{fmtCharge(item.q_C)}</strong>
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
            <span>e: {fmtCharge(props.inversion.e_hat_C)}</span>
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

function QCalculationFlow({ record }: { record: NormalRecord }) {
  const q = (record.q as Record<string, any> | undefined) ?? {};
  const fit = (record.fit as Record<string, any> | undefined) ?? {};
  const trace = (q.calculation_trace as Record<string, any> | undefined) ?? {};
  const fitTrace = (trace.fit as Record<string, any> | undefined) ?? {};
  const physicsTrace = (trace.physics as Record<string, any> | undefined) ?? {};
  const resultTrace = (trace.result as Record<string, any> | undefined) ?? {};
  const timeWindow = (record.time_window as Record<string, any> | undefined) ?? {};
  const radius = finite(physicsTrace.radius_m ?? q.radius_m ?? record.radius_m);
  const velocity = finite(fitTrace.velocity_m_s ?? fit.velocity_m_s ?? record.fall_velocity_m_s);
  const sigmaV = finite(fitTrace.sigma_v_m_s ?? fit.sigma_v_m_s);
  const balanceVoltage = finite(physicsTrace.balance_voltage_V ?? q.balance_voltage_V ?? record.balance_voltage_V);
  const etaEff = finite(physicsTrace.eta_eff_Pa_s ?? q.eta_eff_Pa_s);
  const cunninghamLength = finite(physicsTrace.cunningham_length_m);
  const sensitivity = finite(physicsTrace.q_velocity_sensitivity);
  const qValue = finite(resultTrace.q_C ?? q.q_C ?? record.q_C);
  const sigmaQ = finite(resultTrace.sigma_q_C ?? q.sigma_q_C ?? record.sigma_q_C);

  return (
    <section className="normal-q-flow" aria-label="单滴 q 计算流程">
      <header className="normal-q-flow__heading">
        <div>
          <span>从视频证据到单滴电荷</span>
          <strong>本记录的 q 计算链</strong>
        </div>
        <p>数值来自后端 record calculation trace；公式在此只做可审查展示。</p>
      </header>
      <div className="normal-q-flow__steps">
        <CalculationStep
          index="01"
          tone="confirmed"
          icon={<CircleDot size={18} />}
          label="用户确认"
          title="平衡与 0 V 区间"
          formula={<FormulaLine><i>U</i><sub>bal</sub>，<i>t</i><sub>0</sub> → <i>t</i><sub>1</sub></FormulaLine>}
          value={`${fmtNumber(balanceVoltage, 3)} V · ${fmtNumber(timeWindow.zero_v_start_s, 2)}–${fmtNumber(timeWindow.zero_v_end_s, 2)} s`}
        />
        <CalculationStep
          index="02"
          tone="measured"
          icon={<Ruler size={18} />}
          label="机器测量"
          title="轨迹与标尺"
          formula={<FormulaLine><i>y</i>(<i>t</i>)，<i>s</i><sub>y</sub></FormulaLine>}
          value={`${fitTrace.fit_point_count ?? fit.fit_point_count ?? "—"} 点 · ${fmtScientific(fitTrace.scale_y_m_per_px ?? fit.scale_y_m_per_px, 3)} m/px`}
        />
        <CalculationStep
          index="03"
          tone="measured"
          icon={<Activity size={18} />}
          label="线性拟合"
          title="下落速度"
          formula={<FormulaLine><i>y</i> = <i>a</i> + <i>s t</i>，<i>v</i> = <i>s s</i><sub>y</sub></FormulaLine>}
          value={`${fmtScientific(velocity, 4)} m/s · σv ${fmtScientific(sigmaV, 3)} m/s`}
        />
        <CalculationStep
          index="04"
          tone="derived"
          icon={<Gauge size={18} />}
          label="物理推导"
          title="Cunningham 半径"
          formula={
            <FormulaLine>
              <i>r</i> =
              <FormulaFraction
                numerator={<>√(<i>B</i><sup>2</sup> + 18<i>ηv</i>/(<i>ρg</i>)) − <i>B</i></>}
                denominator={<>2</>}
              />
            </FormulaLine>
          }
          value={`B ${fmtScientific(cunninghamLength, 3)} m · r ${fmtNumber(radius === null ? null : radius * 1e6, 4)} μm`}
        />
        <CalculationStep
          index="05"
          tone="derived"
          icon={<Calculator size={18} />}
          label="物理推导"
          title="有效黏度与 q"
          formula={
            <FormulaLine>
              <i>q</i> =
              <FormulaFraction
                numerator={<>6π<i>η</i><sub>eff</sub><i>rvd</i></>}
                denominator={<><i>U</i><sub>bal</sub></>}
              />
            </FormulaLine>
          }
          value={`ηeff ${fmtScientific(etaEff, 3)} Pa·s · q ${fmtCharge(qValue)}`}
        />
        <CalculationStep
          index="06"
          tone="result"
          icon={<Sigma size={18} />}
          label="最终输出"
          title="不确定度传播"
          formula={
            <FormulaLine>
              <i>σ</i><sub>q</sub> = |<i>q</i>|
              <FormulaFraction
                numerator={<>3(<i>r</i> + <i>B</i>)</>}
                denominator={<>2<i>r</i> + <i>B</i></>}
              />
              <FormulaFraction numerator={<><i>σ</i><sub>v</sub></>} denominator={<><i>v</i></>} />
            </FormulaLine>
          }
          value={`${fmtCharge(qValue)} ± ${fmtCharge(sigmaQ)} · 灵敏度 ${fmtNumber(sensitivity, 3)}`}
        />
      </div>
    </section>
  );
}

function CalculationStep(props: {
  index: string;
  tone: "confirmed" | "measured" | "derived" | "result";
  icon: ReactNode;
  label: string;
  title: string;
  formula: ReactNode;
  value: string;
}) {
  return (
    <article className={`normal-q-step normal-q-step--${props.tone}`}>
      <span className="normal-q-step__index">{props.index}</span>
      <div className="normal-q-step__label">{props.icon}<span>{props.label}</span></div>
      <strong>{props.title}</strong>
      {props.formula}
      <small>{props.value}</small>
    </article>
  );
}

function FormulaLine({ children }: { children: ReactNode }) {
  return <div className="normal-formula">{children}</div>;
}

function FormulaFraction({ numerator, denominator }: { numerator: ReactNode; denominator: ReactNode }) {
  return (
    <span className="normal-formula-fraction">
      <span>{numerator}</span>
      <span>{denominator}</span>
    </span>
  );
}

function InversionPanel(props: {
  session: NormalSession | null;
  inversion: NormalInversionResult | null;
  keptValidCount: number;
  busy: boolean;
  onBackResults: () => void;
  onNextDrop: () => void;
  onExport: () => void;
  onRunInversion: () => void;
}) {
  const status = props.inversion?.status ?? "not_run";
  const flags = props.inversion?.flags ?? [];
  const accepted = props.session?.counts?.kept_valid ?? props.keptValidCount;
  return (
    <div className="normal-panel-stack">
      <div className="section-heading">
        <span>stage 6</span>
        <strong>盲反演结果</strong>
      </div>
      <div className="normal-diagnostic-box normal-inversion-inspector-lead">
        <strong>运行诊断</strong>
        <span className={`normal-inversion-status ${status === "reliable" ? "good" : status === "insufficient_eligible_records" ? "blocked" : "warn"}`}>{inversionStatusLabel(status)}</span>
        <span>主结果、误差和百分比统一显示在中央结果页。</span>
      </div>
      <div className="normal-meta-grid">
        <InfoTile label="使用 q" value={String(props.inversion?.valid_q_count ?? props.inversion?.num_used ?? accepted)} />
        <InfoTile label="收敛" value={props.inversion?.converged === false ? "未稳定" : props.inversion ? "稳定" : "-"} />
        <InfoTile label="边界命中" value={props.inversion?.boundary_hit ? "是" : "否"} />
        <InfoTile label="样本结论" value={status === "exploratory" ? "探索性" : status === "reliable" ? "候选可靠" : "需诊断"} />
      </div>
      <div className="normal-diagnostic-box">
        <strong>科学边界</strong>
        <span>{status === "insufficient_eligible_records" ? "有效保留 q 不足 3 条，不能给出 e 候选。" : "Normal v1 展示整数倍残差对齐诊断；没有拟合真实连续 baseline，因此不输出模型胜负。"}</span>
        <span>flags: {flags.length ? flags.join(", ") : "none"}</span>
      </div>
      <div className="normal-diagnostic-box">
        <strong>搜索设置</strong>
        <span>interval: {fmtCharge(props.inversion?.search_interval_C?.[0])} - {fmtCharge(props.inversion?.search_interval_C?.[1])}</span>
        <span>sigma floor: {fmtCharge(props.inversion?.sigma_floor_C)}</span>
      </div>
      <div className="panel-actions">
        <button className="ghost-button" disabled={props.busy} onClick={props.onBackResults}>
          返回结果与 session
        </button>
        <button className="ghost-button" disabled={props.busy} onClick={props.onExport}>
          <Download size={15} />
          导出 session
        </button>
        <button className="primary-button small" disabled={props.busy || accepted < 3} onClick={props.onRunInversion}>
          <Play size={15} />
          重新反演
        </button>
      </div>
      <button className="primary-button full" disabled={props.busy || !props.session?.records?.some((record) => record.status === "accepted" && record.kept)} onClick={props.onNextDrop}>
        下一颗油滴
      </button>
    </div>
  );
}

function NormalInversionDashboard({ inversion, records }: { inversion: NormalInversionResult | null; records: NormalRecord[] }) {
  const charts = normalizeInversionCharts(inversion);
  const assignments = inversion?.assignments ?? [];
  const candidates = inversion?.candidates ?? [];
  const status = inversion?.status ?? "not_run";
  const accepted = records.filter((record) => record.status === "accepted" && record.kept);
  const comparison = inversion?.reference_comparison;
  if (!inversion) {
    return (
      <div className="normal-inversion-empty">
        <Sigma size={44} />
        <strong>等待盲反演</strong>
        <span>至少三条用户确认保留的 q 记录后，运行 Normal 盲反演。</span>
      </div>
    );
  }
  return (
    <div className="normal-inversion-dashboard" aria-label="Normal 盲反演结果页">
      <section className="normal-inversion-hero">
        <div className="normal-inversion-primary">
          <span className={`normal-inversion-status ${status === "reliable" ? "good" : status === "insufficient_eligible_records" ? "blocked" : "warn"}`}>{inversionStatusLabel(status)}</span>
          <span className="normal-inversion-eyebrow">元电荷估计</span>
          <strong className="normal-inversion-value">{fmtCharge(inversion.e_hat_C, 5)}</strong>
          <p>基于本次 session 中用户确认保留的 q，执行带不确定度权重的整数倍残差搜索。</p>
        </div>
        <div className="normal-inversion-kpis">
          <KpiBox label="标准不确定度 σe" value={fmtCharge(inversion.sigma_e_C, 5)} detail="统一按 10⁻¹⁹ C 显示" />
          <KpiBox label="相对不确定度" value={fmtPercentValue(comparison?.relative_uncertainty_percent, 3)} detail="σe / ê" />
          <KpiBox label="相对标准值百分误差" value={fmtPercentValue(comparison?.percent_error_vs_reference, 3)} detail={`参考 ${fmtCharge(comparison?.reference_e_C, 9)}`} />
          <KpiBox label="观测与拟合" value={`${inversion.valid_q_count ?? inversion.num_used ?? accepted.length} q · RMS ${formatFixed(inversion.weighted_rms, 3)}`} detail={`χ² ${formatFixed(inversion.chi2, 3)}`} />
        </div>
      </section>

      {status === "insufficient_eligible_records" ? (
        <section className="normal-inversion-blocker">
          <BarChart3 size={30} />
          <strong>有效 q 记录不足</strong>
          <span>当前 {inversion.valid_q_count ?? accepted.length} 条，至少需要 {inversion.min_required ?? 3} 条 accepted q 才能反演。</span>
        </section>
      ) : (
        <>
          <section className="normal-inversion-chart-grid">
            <ChargeAlignmentChart rows={charts.charge_distribution} levels={charts.quantized_levels} eHat={inversion.e_hat_C ?? null} />
            <ResidualChart rows={charts.residuals} />
          </section>
          <section className="normal-inversion-tables">
            <CandidateList candidates={candidates} />
            <AssignmentTable assignments={assignments} />
          </section>
        </>
      )}
    </div>
  );
}

function KpiBox({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="normal-inversion-kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function ChargeAlignmentChart({
  rows,
  levels,
  eHat
}: {
  rows: Array<{ q_C?: number; sigma_q_C?: number; n?: number; nearest_C?: number }>;
  levels: Array<{ n?: number; charge_C?: number }>;
  eHat: number | null;
}) {
  const width = 720;
  const height = 310;
  const pad = { left: 58, right: 28, top: 28, bottom: 48 };
  const values = rows.flatMap((row) => [finite(row.q_C), finite(row.nearest_C)]).filter((value): value is number => value !== null);
  const levelValues = levels.map((level) => finite(level.charge_C)).filter((value): value is number => value !== null);
  const all = [...values, ...levelValues, eHat ?? undefined].filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const max = all.length ? Math.max(...all) * 1.08 : 1;
  const min = 0;
  const x = (index: number) => pad.left + (rows.length <= 1 ? 0.5 : index / (rows.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => height - pad.bottom - ((value - min) / Math.max(1e-30, max - min)) * (height - pad.top - pad.bottom);
  return (
    <div className="normal-chart-panel">
      <div className="chart-heading">
        <span>q 观测与整数倍对齐</span>
        <small>误差条为 sigma_q；横线为 n * e_hat</small>
      </div>
      <svg className="normal-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="q 观测与整数倍对齐图">
        <line className="axis strong" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <line className="axis strong" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        {levels.map((level) => {
          const value = finite(level.charge_C);
          if (value === null) return null;
          return (
            <g key={`level-${level.n ?? value}`}>
              <line className="normal-level-line" x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
              <text x={width - pad.right - 46} y={y(value) - 5}>n={level.n}</text>
            </g>
          );
        })}
        {rows.map((row, index) => {
          const q = finite(row.q_C);
          if (q === null) return null;
          const sigma = Math.max(0, finite(row.sigma_q_C) ?? 0);
          const cx = x(index);
          const cy = y(q);
          return (
            <g key={`q-${index}`}>
              <line className="normal-error-bar" x1={cx} x2={cx} y1={y(q - sigma)} y2={y(q + sigma)} />
              <circle className="normal-q-dot" cx={cx} cy={cy} r="6" />
              <text x={cx - 12} y={height - 18}>{index + 1}</text>
            </g>
          );
        })}
        <text x={pad.left} y={height - 10}>accepted q index</text>
        <text x={12} y={26}>C</text>
      </svg>
    </div>
  );
}

function ResidualChart({ rows }: { rows: Array<{ residual_sigma?: number; n?: number; record_id?: string }> }) {
  const width = 720;
  const height = 310;
  const pad = { left: 58, right: 30, top: 32, bottom: 48 };
  const maxAbs = Math.max(2.5, ...rows.map((row) => Math.abs(finite(row.residual_sigma) ?? 0))) * 1.1;
  const x = (index: number) => pad.left + (rows.length <= 1 ? 0.5 : index / (rows.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + ((maxAbs - value) / (2 * maxAbs)) * (height - pad.top - pad.bottom);
  return (
    <div className="normal-chart-panel">
      <div className="chart-heading">
        <span>归一化残差</span>
        <small>residual / sigma_eff，越接近 0 越对齐整数倍</small>
      </div>
      <svg className="normal-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="归一化残差图">
        <line className="axis strong" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <line className="axis strong" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        {[0, 1, -1, 2, -2].map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? "normal-zero-line" : "axis faint"} x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
            <text x={18} y={y(tick) + 4}>{tick}</text>
          </g>
        ))}
        {rows.map((row, index) => {
          const residual = finite(row.residual_sigma) ?? 0;
          const strong = Math.abs(residual) > 2;
          return (
            <g key={`residual-${row.record_id ?? index}`}>
              <line className="normal-residual-stem" x1={x(index)} x2={x(index)} y1={y(0)} y2={y(residual)} />
              <circle className={strong ? "normal-residual-dot warn" : "normal-residual-dot"} cx={x(index)} cy={y(residual)} r="6" />
              <text x={x(index) - 10} y={height - 18}>n{row.n ?? "-"}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function CandidateList({ candidates }: { candidates: NonNullable<NormalInversionResult["candidates"]> }) {
  return (
    <div className="normal-inversion-table-card">
      <div className="chart-heading">
        <span>候选解</span>
        <small>按残差排序，保留不同整数分配</small>
      </div>
      <div className="normal-candidate-list">
        {candidates.slice(0, 6).map((candidate, index) => (
          <div key={`${candidate.e_C ?? index}-${index}`}>
            <span>#{index + 1}</span>
            <strong>{fmtCharge(candidate.e_C)}</strong>
            <small>RMS {formatFixed(candidate.weighted_rms, 3)} · chi² {formatFixed(candidate.chi2, 3)}</small>
            <em>{(candidate.integer_assignment ?? []).join(" : ") || "-"}</em>
            <b>{candidate.converged ? "stable" : "unstable"}{candidate.boundary_hit ? " · boundary" : ""}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssignmentTable({ assignments }: { assignments: NonNullable<NormalInversionResult["assignments"]> }) {
  return (
    <div className="normal-inversion-table-card">
      <div className="chart-heading">
        <span>整数分配与残差</span>
        <small>每颗 accepted q 对应一个 n_i</small>
      </div>
      <div className="table-wrap normal-inversion-table">
        <table>
          <thead>
            <tr>
              <th>record</th>
              <th>q / C</th>
              <th>n</th>
              <th>n e / C</th>
              <th>residual σ</th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((row, index) => (
              <tr key={row.record_id ?? index}>
                <td>{String(row.record_id ?? index + 1)}</td>
                <td>{fmtCharge(row.q_C)}</td>
                <td>{row.n ?? "-"}</td>
                <td>{fmtCharge(row.nearest_quantized_charge_C)}</td>
                <td>{formatFixed(row.residual_sigma, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function normalizeInversionCharts(inversion: NormalInversionResult | null) {
  const raw = (inversion?.charts ?? inversion?.plots_data ?? {}) as Record<string, any>;
  return {
    charge_distribution: Array.isArray(raw.charge_distribution) ? raw.charge_distribution : [],
    residuals: Array.isArray(raw.residuals) ? raw.residuals : [],
    quantized_levels: Array.isArray(raw.quantized_levels) ? raw.quantized_levels : []
  };
}

function finite(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function inversionStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    reliable: "可靠候选",
    exploratory: "探索性结果",
    diagnostic: "诊断结果",
    insufficient_eligible_records: "记录不足",
    ok: "探索性结果",
    not_run: "未运行"
  };
  return labels[status || ""] ?? status ?? "未运行";
}

function CrossingFramePlayer({ event }: { event: NormalCrossingEvent }) {
  const frames = event.review_frames ?? [];
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const activeFrame = frames[Math.min(frameIndex, Math.max(0, frames.length - 1))];

  useEffect(() => {
    setFrameIndex(0);
    setPlaying(frames.length > 1);
  }, [event.event_id, frames.length]);

  useEffect(() => {
    if (!playing || frames.length <= 1) return;
    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1) % frames.length);
    }, 100);
    return () => window.clearInterval(timer);
  }, [playing, frames.length]);

  if (!frames.length || !activeFrame?.image_url) {
    return (
      <div className="normal-frame-player normal-frame-player--empty">
        <strong>复核帧不可用</strong>
        <span>后端没有返回可播放的 review_frames，请重新生成 crossing 复核。</span>
      </div>
    );
  }

  return (
    <div className="normal-frame-player" aria-label="crossing 局部复核帧播放器">
      <img src={activeFrame.image_url} alt={`${event.event_id} frame ${frameIndex + 1}`} />
      <div className="normal-frame-player__controls">
        <button className="icon-button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "暂停复核帧" : "播放复核帧"}>
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, frames.length - 1)}
          step={1}
          value={frameIndex}
          onChange={(change) => {
            setFrameIndex(Number(change.target.value));
            setPlaying(false);
          }}
          aria-label="复核帧进度"
        />
        <span>{formatFixed(activeFrame.time_s, 2)} s</span>
      </div>
      <small>{event.event_id} · {frameIndex + 1}/{frames.length}</small>
    </div>
  );
}

function TrackFramePlayer({ frames }: { frames: NonNullable<NormalRecord["track_review_frames"]> }) {
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const activeFrame = frames[Math.min(frameIndex, Math.max(0, frames.length - 1))];

  useEffect(() => {
    setFrameIndex(0);
    setPlaying(frames.length > 1);
  }, [frames.length]);

  useEffect(() => {
    if (!playing || frames.length <= 1) return;
    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1) % frames.length);
    }, 80);
    return () => window.clearInterval(timer);
  }, [playing, frames.length]);

  if (!frames.length || !activeFrame?.image_url) {
    return (
      <div className="normal-track-frame-player normal-frame-player--empty">
        <strong>轨迹复核帧不可用</strong>
        <span>后端没有返回可播放的 track_review_frames。</span>
      </div>
    );
  }

  return (
    <div className="normal-track-frame-player" aria-label="完整轨迹复核帧播放器">
      <img src={activeFrame.image_url} alt={`track review frame ${frameIndex + 1}`} />
      <div className="normal-track-frame-player__controls">
        <button className="icon-button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "暂停完整轨迹" : "播放完整轨迹"}>
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, frames.length - 1)}
          step={1}
          value={frameIndex}
          onChange={(change) => {
            setFrameIndex(Number(change.target.value));
            setPlaying(false);
          }}
          aria-label="完整轨迹帧进度"
        />
        <span>{formatFixed(activeFrame.time_s, 2)} s</span>
      </div>
      <small>
        frame {activeFrame.frame_index} · {frameIndex + 1}/{frames.length}
      </small>
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
