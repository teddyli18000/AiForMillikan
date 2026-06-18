import { RefObject, useEffect, useMemo, useState } from "react";
import type { NormalRecord, VideoMetadata } from "../../types";

type Props = {
  videoRef: RefObject<HTMLVideoElement | null>;
  record: NormalRecord | null;
  metadata: VideoMetadata | null;
};

export function CrossingReview({ videoRef, record, metadata }: Props) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [looping, setLooping] = useState(false);
  const events = useMemo(() => record?.crossing_events ?? [], [record]);
  const active = events.find((event) => String(event.id) === activeId);
  const fps = metadata?.fps || 30;

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !active || !looping) return;
    const start = Number(active.review_start_frame) / fps;
    const end = Number(active.review_end_frame) / fps;
    let disposed = false;
    const onTime = () => {
      if (disposed) return;
      if (video.currentTime >= end) {
        video.currentTime = start;
        void video.play();
      }
    };
    const onPause = () => setLooping(false);
    const onSeeking = () => {
      if (video.currentTime < start - 0.05 || video.currentTime > end + 0.05) setLooping(false);
    };
    video.currentTime = start;
    void video.play();
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("pause", onPause);
    video.addEventListener("seeking", onSeeking);
    return () => {
      disposed = true;
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("seeking", onSeeking);
    };
  }, [active, looping, fps, videoRef]);

  if (!record || events.length === 0) return null;

  return (
    <section className="normal-step-card">
      <div className="normal-step-heading">
        <span>复核</span>
        <div>
          <h3>跨网格片段</h3>
          <p>点击事件会真实循环播放穿越前后短区间；退出或手动 seek 会停止循环。</p>
        </div>
      </div>
      <div className="crossing-list">
        {events.map((event) => (
          <button
            key={String(event.id)}
            className={activeId === event.id ? "crossing-chip active" : "crossing-chip"}
            onClick={() => {
              setActiveId(String(event.id));
              setLooping(true);
            }}
          >
            {String(event.id)} · {String(event.start_frame)}-{String(event.end_frame)}
          </button>
        ))}
        {looping && <span className="loop-badge">正在循环复核</span>}
        <button className="ghost-button" onClick={() => setLooping(false)}>退出复核</button>
      </div>
    </section>
  );
}
