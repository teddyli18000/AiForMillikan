import { RefObject } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import type { NormalBoundarySuggestion, NormalGrid, NormalRecord, NormalTarget, VideoMetadata } from "../../types";
import { TargetSelector } from "./TargetSelector";
import { TrackingOverlay } from "./TrackingOverlay";

type Props = {
  videoRef: RefObject<HTMLVideoElement | null>;
  videoUrl: string;
  metadata: VideoMetadata | null;
  currentTime: number;
  isPlaying: boolean;
  boundary: NormalBoundarySuggestion | null;
  grid: NormalGrid | null;
  target: NormalTarget | null;
  activeRecord: NormalRecord | null;
  selecting: boolean;
  onTimeUpdate: (time: number) => void;
  onLoadedMetadata: () => void;
  onTogglePlay: () => void;
  onNudge: (delta: number) => void;
  onSeekBoundary: (kind: "selection" | "start" | "end") => void;
  onTarget: (target: NormalTarget) => void;
};

export function NormalVideoPlayer(
  {
    videoRef,
    videoUrl,
    metadata,
    currentTime,
    isPlaying,
    boundary,
    grid,
    target,
    activeRecord,
    selecting,
    onTimeUpdate,
    onLoadedMetadata,
    onTogglePlay,
    onNudge,
    onSeekBoundary,
    onTarget,
  }: Props
) {
  return (
    <section className="normal-video-panel">
      <div className="normal-video-shell">
        <video
          ref={videoRef}
          className="normal-video"
          src={videoUrl}
          controls={false}
          onLoadedMetadata={onLoadedMetadata}
          onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime)}
        />
        <TrackingOverlay videoRef={videoRef} metadata={metadata} boundary={boundary} grid={grid} target={target} record={activeRecord} currentTime={currentTime} />
        {selecting && <TargetSelector videoRef={videoRef} metadata={metadata} onTarget={onTarget} />}
      </div>
      <div className="normal-player-controls">
        <button className="icon-button" onClick={onTogglePlay} aria-label={isPlaying ? "暂停" : "播放"}>
          {isPlaying ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button className="ghost-button" disabled={!boundary} onClick={() => onSeekBoundary("selection")}>检查框选帧</button>
        <button className="ghost-button" disabled={!boundary} onClick={() => onSeekBoundary("start")}>检查开始时间</button>
        <button className="ghost-button" disabled={!boundary} onClick={() => onSeekBoundary("end")}>检查结束时间</button>
        <button className="ghost-button" onClick={() => onNudge(-1)}><SkipBack size={15} /> -1.0 s</button>
        <button className="ghost-button" onClick={() => onNudge(-0.1)}>-0.1 s</button>
        <span className="time-chip">{currentTime.toFixed(2)} s</span>
        <button className="ghost-button" onClick={() => onNudge(0.1)}>+0.1 s</button>
        <button className="ghost-button" onClick={() => onNudge(1)}>+1.0 s <SkipForward size={15} /></button>
      </div>
    </section>
  );
}
