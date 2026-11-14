import type { DragEvent, MouseEvent, SyntheticEvent } from "react";
import type { VideoBox, VideoPoint } from "./videoGeometry";
import type {
  NormalBoundary,
  VideoMetadata
} from "../../types";
import { clientPointToVideoPoint, getContainedVideoMetrics, videoBoxToOverlayStyle } from "./videoGeometry";
import {
  clampBoundary,
  clampSelectionTime,
  gridParameterKeys,
  physicsParameterKeys
} from "./workspaceModel";
import { desktopApi } from "../../lib/desktopApi";
import type { WorkspaceDesk } from "./workspaceDesk";

function makeVideoImport(desk: WorkspaceDesk) {
  const { setStage, metadata, setMetadata, setVideoPath, setVideoUrl, setBoundary } = desk;
  const { setBoundaryEdited, setGrid, setSelectionBox, setBalanceVoltage, setBalanceConfirmed, setOverrideFields } = desk;
  const { setSelectedRecordId, setRetrySourceRecordId, setCurrentCrossing, setInversion, setProgress, setBusy } = desk;
  const { message, setMessage, setCurrentTime, setDuration } = desk;

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
  return { inspectVideo, openVideo, onDrop };
}

function makePlaybackControls(desk: WorkspaceDesk) {
  const { videoRef, stage, metadata, boundary, setBoundary, setBoundaryEdited } = desk;
  const { selectionTime, setSelectionTime, setSelectedRecordId, setCurrentCrossing, setInversion, setMessage } = desk;
  const { currentTime, setCurrentTime, duration } = desk;

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

  const jumpTo = (time: number, metadataOverride?: VideoMetadata | null) => {
    seekVideoTo(time, metadataOverride, stage === "target");
  };

  const dropReviewAndInversion = () => {
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
      dropReviewAndInversion();
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
  return { seekVideoTo, jumpTo, dropReviewAndInversion, setSelectionFrameTime, playerJumpTo, togglePlay, adjustBoundary, adjustSelectionTime };
}

function makeSelectionDrag(desk: WorkspaceDesk) {
  const { videoRef, overlayRef, stage, metadata, selectionBox, setSelectionBox } = desk;
  const { selectionAnchor, setSelectionAnchor, setBalanceConfirmed, setSelectedRecordId, setCurrentCrossing, setInversion } = desk;
  const { setMessage } = desk;

  const overlayGeometry = () => {
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
    const geometry = overlayGeometry();
    if (!geometry) return null;
    return clientPointToVideoPoint(event.clientX, event.clientY, geometry.overlayRect, geometry.metrics, options);
  };

  const videoBoxStyle = (box: VideoBox) => {
    const geometry = overlayGeometry();
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
  return { overlayGeometry, clientToVideoPoint, videoBoxStyle, onSelectionDown, onSelectionMove, endSelection };
}

function makeParameterInputs(desk: WorkspaceDesk) {
  const { defaultParameters, setBoundary, setBoundaryEdited, grid, overrideFields, setSelectedRecordId } = desk;
  const { setCurrentCrossing, setInversion } = desk;

  const overridesForWorker = () => {
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

  const parameterInputValue = (key: string) => {
    if (overrideFields[key] !== undefined) {
      return overrideFields[key];
    }
    const source = physicsParameterKeys.includes(key) ? defaultParameters?.physics : defaultParameters?.grid;
    const value = source?.[key];
    return value === undefined || value === null ? "" : String(value);
  };

  const noteBoundaryEdit = (nextBoundary: NormalBoundary) => {
    setBoundaryEdited(true);
    setBoundary(nextBoundary);
    setSelectedRecordId(null);
    setCurrentCrossing(null);
    setInversion(null);
  };
  return { overridesForWorker, parameterInputValue, noteBoundaryEdit };
}

function makeVideoElementHandlers(desk: WorkspaceDesk) {
  const { stage, metadata, boundary, selectionTime, setSelectionTime, currentTime } = desk;
  const { setCurrentTime, duration, setDuration } = desk;


  const onLoadedMetadata = (event: SyntheticEvent<HTMLVideoElement>) => {
    const player = event.currentTarget;
    setDuration(player.duration || metadata?.duration_s || 0);
    const initialTime = stage === "target"
      ? clampSelectionTime(selectionTime, boundary, metadata)
      : stage === "boundary"
        ? Number(boundary.zero_v_start_s || 0)
        : player.currentTime || 0;
    if (stage === "target" || stage === "boundary") {
      player.currentTime = initialTime;
    }
    setCurrentTime(initialTime);
  };

  const onTimeUpdate = (event: SyntheticEvent<HTMLVideoElement>) => {
    const player = event.currentTarget;
    const time = player.currentTime || 0;
    if (stage === "target") {
      const safe = clampSelectionTime(time, boundary, metadata);
      if (Math.abs(safe - time) > 0.01) {
        player.currentTime = safe;
      }
      player.pause();
      setSelectionTime(safe);
      setCurrentTime(safe);
    } else {
      setCurrentTime(time);
    }
  };

  return { onLoadedMetadata, onTimeUpdate };
}

export type VideoControls = ReturnType<typeof useVideoControls>;

export function useVideoControls(desk: WorkspaceDesk) {
  return {
    ...makeVideoImport(desk),
    ...makePlaybackControls(desk),
    ...makeSelectionDrag(desk),
    ...makeParameterInputs(desk),
    ...makeVideoElementHandlers(desk)
  };
}
