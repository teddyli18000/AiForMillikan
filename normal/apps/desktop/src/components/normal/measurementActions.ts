import type {
  NormalBoundary,
  NormalCrossingEvent
} from "../../types";
import {
  clampBoundary,
  clampSelectionTime
} from "./workspaceModel";
import { desktopApi } from "../../lib/desktopApi";
import type { WorkspaceDesk } from "./workspaceDesk";

import type { VideoControls } from "./videoControls";
import type { RecordRestore } from "./recordRestore";

function makeStageActions(desk: WorkspaceDesk, video: VideoControls, restore: RecordRestore) {
  const { setStage, session, setSession, setDefaultParameters, metadata, setMetadata } = desk;
  const { videoPath, videoUrl, setVideoUrl, boundary, setBoundary, boundaryEdited } = desk;
  const { setBoundaryEdited, grid, setGrid, selectionTime, setSelectionTime, selectionBox } = desk;
  const { setSelectionBox, balanceVoltage, balanceConfirmed, setSelectedRecordId, retrySourceRecordId, setRetrySourceRecordId } = desk;
  const { setCurrentCrossing, setInversion, setProgress, setBusy, message, setMessage } = desk;

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
      video.seekVideoTo(nextSelectionTime, metadata, true);
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
    video.setSelectionFrameTime(safeSelectionTime, { clearDownstream: false });
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
        parameter_overrides: video.overridesForWorker()
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
  return { startPrepare, confirmBoundary, selectTargetAndTrack };
}

function makeReviewActions(desk: WorkspaceDesk, restore: RecordRestore) {
  const { setStage, session, setSession, setSelectedRecordId, currentCrossing, setCurrentCrossing } = desk;
  const { setInversion, setProgress, setBusy, message, setMessage, selectedRecord } = desk;
  const { crossings } = desk;

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
        await restore.reopenAtBoundary(response.record, response.session);
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
        await restore.reopenAtBoundary(selectedRecord, nextSession);
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
  return { prepareCrossingReview, submitCrossingReview, acceptRecord };
}

function makeResultActions(desk: WorkspaceDesk) {
  const { setStage, session, setSession, inversion, setInversion, setProgress } = desk;
  const { setBusy, message, setMessage } = desk;

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
  return { runInversion, exportSession };
}

export function useMeasurementActions(desk: WorkspaceDesk, video: VideoControls, restore: RecordRestore) {
  return {
    ...makeStageActions(desk, video, restore),
    ...makeReviewActions(desk, restore),
    ...makeResultActions(desk)
  };
}
