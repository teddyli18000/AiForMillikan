import type { VideoBox } from "./videoGeometry";
import type {
  NormalBoundary,
  NormalGrid,
  NormalRecord,
  NormalSession,
  VideoMetadata
} from "../../types";
import {
  clampSelectionTime,
  flatParameterOverrides,
  type MeasurementStage
} from "./workspaceModel";
import { desktopApi } from "../../lib/desktopApi";
import type { WorkspaceDesk } from "./workspaceDesk";

import type { VideoControls } from "./videoControls";

function makeRecordRestore(desk: WorkspaceDesk, video: VideoControls) {
  const { setStage, session, setSession, metadata, setMetadata, videoPath } = desk;
  const { setVideoPath, setVideoUrl, boundary, setBoundary, setBoundaryEdited, grid } = desk;
  const { setGrid, selectionTime, setSelectionTime, setSelectionBox, setBalanceVoltage, setBalanceConfirmed } = desk;
  const { setOverrideFields, setRetrySourceRecordId, setCurrentCrossing, setBusy, message, setMessage } = desk;
  const { setDuration } = desk;

  const loadRecordForEditing = async (record: NormalRecord, restoredSession: NormalSession | null | undefined, destination: MeasurementStage, markRetry: boolean): Promise<boolean> => {
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
    setOverrideFields(flatParameterOverrides(overrides ?? {}));
    setRetrySourceRecordId(markRetry ? String(restoredAdjustment.record_id ?? record.record_id) : null);
    setCurrentCrossing(null);
    setStage(destination);
    video.seekVideoTo(destination === "boundary" ? Number(nextBoundary.zero_v_start_s ?? restoredSelectionTime) : restoredSelectionTime, nextMetadata ?? metadata, destination === "target");
    return true;
  };

  const reopenAtBoundary = (record: NormalRecord, restoredSession?: NormalSession | null) => {
    return loadRecordForEditing(record, restoredSession, "boundary", true);
  };

  const backToBoundary = (record?: NormalRecord | null) => {
    if (record) {
      void loadRecordForEditing(record, undefined, "boundary", true).then((restored) => {
        if (restored) setMessage("已恢复该测量，可调整区间后重新追踪。");
      });
      return;
    }
    setStage("boundary");
    setCurrentCrossing(null);
    setMessage("已返回 确认零电压区间。会在上次确认基础上微调；确认修改后需重新框选并追踪。");
    video.jumpTo(boundary.zero_v_start_s);
  };

  const backToTarget = (record?: NormalRecord | null) => {
    if (record) {
      void loadRecordForEditing(record, undefined, "target", true).then((restored) => {
        if (restored) setMessage("已恢复该测量，请调整框选后重新追踪。");
      });
      return;
    }
    setStage("target");
    video.dropReviewAndInversion();
    const clampedTime = clampSelectionTime(selectionTime || boundary.zero_v_start_s, boundary, metadata);
    setSelectionTime(clampedTime);
    setMessage("已返回框选目标。保留已确认边界和参数；修改框选后会重新追踪。");
    video.seekVideoTo(clampedTime, metadata, true);
  };
  return { loadRecordForEditing, reopenAtBoundary, backToBoundary, backToTarget };
}

function makeNextDroplet(desk: WorkspaceDesk, video: VideoControls) {
  const { setStage, session, setSession, metadata, setMetadata, videoPath } = desk;
  const { setVideoPath, videoUrl, setVideoUrl, boundary, setBoundary, setBoundaryEdited } = desk;
  const { grid, setGrid, selectionTime, setSelectionTime, setSelectionBox, setSelectionAnchor } = desk;
  const { setBalanceVoltage, setBalanceConfirmed, setOverrideFields, setSelectedRecordId, setRetrySourceRecordId, setCurrentCrossing } = desk;
  const { setInversion, setProgress, setBusy, message, setMessage, setCurrentTime } = desk;
  const { setDuration, setNextDropDialogOpen, selectedRecord } = desk;

  const startFreshDroplet = () => {
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
      startFreshDroplet();
      setMetadata(nextMetadata ?? null);
      setVideoPath(typeof activeVideo?.path === "string" ? activeVideo.path : videoPath);
      setVideoUrl(typeof activeVideo?.video_url === "string" ? activeVideo.video_url : videoUrl);
      setGrid((activeVideo?.grid as NormalGrid | undefined) ?? grid);
      setBoundary(nextBoundary);
      setBoundaryEdited(false);
      const previousVoltage = activeVideo?.previous_balance_voltage_V;
      setBalanceVoltage(previousVoltage === undefined || previousVoltage === null ? "" : String(previousVoltage));
      setBalanceConfirmed(false);
      setOverrideFields(flatParameterOverrides(previousOverrides));
      const nextSelectionTime = clampSelectionTime(Number(nextBoundary.zero_v_start_s ?? selectionTime), nextBoundary, nextMetadata ?? metadata);
      setSelectionTime(nextSelectionTime);
      video.seekVideoTo(nextSelectionTime, nextMetadata ?? metadata, true);
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
      startFreshDroplet();
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
  return { startFreshDroplet, nextDropSameVideo, nextDropDifferentVideo };
}

export type RecordRestore = ReturnType<typeof useRecordRestore>;

export function useRecordRestore(desk: WorkspaceDesk, video: VideoControls) {
  return {
    ...makeRecordRestore(desk, video),
    ...makeNextDroplet(desk, video)
  };
}
