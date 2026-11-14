import { useEffect, useState } from "react";
import { Pause, Play } from "lucide-react";
import type { NormalCrossingEvent, NormalRecord } from "../../types";
import { fixedOrDash } from "./workspaceModel";

// 两个播放器看着差不多，定时节奏和 aria 文案不一样，先各留各的。

export function CrossingFramePlayer({ event }: { event: NormalCrossingEvent }) {
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
        <span>请重新生成过线复核片段。</span>
      </div>
    );
  }

  return (
    <div className="normal-frame-player" aria-label="过线片段播放器">
      <img src={activeFrame.image_url} alt={`过线片段第 ${frameIndex + 1} 帧`} />
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
        <span>{fixedOrDash(activeFrame.time_s, 2)} s</span>
      </div>
      <small>第 {frameIndex + 1} / {frames.length} 帧</small>
    </div>
  );
}

export function TrackFramePlayer({ frames }: { frames: NonNullable<NormalRecord["track_review_frames"]> }) {
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
        <span>请重新追踪以生成复核画面。</span>
      </div>
    );
  }

  return (
    <div className="normal-track-frame-player" aria-label="完整轨迹复核帧播放器">
      <img src={activeFrame.image_url} alt={`轨迹复核第 ${frameIndex + 1} 帧`} />
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
        <span>{fixedOrDash(activeFrame.time_s, 2)} s</span>
      </div>
      <small>
        第 {frameIndex + 1} / {frames.length} 帧
      </small>
    </div>
  );
}
