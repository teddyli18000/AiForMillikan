import { PointerEvent, RefObject, useState } from "react";
import type { NormalTarget, VideoMetadata } from "../../types";

type Props = {
  videoRef: RefObject<HTMLVideoElement | null> | ((instance: HTMLVideoElement | null) => void) | null;
  metadata: VideoMetadata | null;
  onTarget: (target: NormalTarget) => void;
};

type Point = { x: number; y: number };

export function TargetSelector({ videoRef, metadata, onTarget }: Props) {
  const [start, setStart] = useState<Point | null>(null);
  const [current, setCurrent] = useState<Point | null>(null);

  const video = refValue(videoRef);

  const begin = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = localPoint(event, event.currentTarget);
    setStart(point);
    setCurrent(point);
  };

  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!start) return;
    setCurrent(localPoint(event, event.currentTarget));
  };

  const end = (event: PointerEvent<HTMLDivElement>) => {
    if (!start || !current || !video || !metadata) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    const box = normalizeBox(start, current);
    if (box.width < 8 || box.height < 8) {
      setStart(null);
      setCurrent(null);
      return;
    }
    const sourceBox = displayToSourceBox(box, video);
    onTarget({
      display_box: box,
      source_video_box: sourceBox,
      source_center: { x: sourceBox.x + sourceBox.width / 2, y: sourceBox.y + sourceBox.height / 2 },
      target_frame: Math.round(video.currentTime * metadata.fps),
      video_natural_width: video.videoWidth || metadata.width,
      video_natural_height: video.videoHeight || metadata.height,
    });
    setStart(null);
    setCurrent(null);
  };

  const box = start && current ? normalizeBox(start, current) : null;

  return (
    <div className="target-selector" onPointerDown={begin} onPointerMove={move} onPointerUp={end}>
      <div className="selector-hint">拖拽框选油滴</div>
      {box && <div className="selection-box" style={{ left: box.x, top: box.y, width: box.width, height: box.height }} />}
    </div>
  );
}

function refValue(ref: Props["videoRef"]): HTMLVideoElement | null {
  if (!ref || typeof ref === "function") return null;
  return ref.current;
}

function localPoint(event: PointerEvent, element: HTMLElement): Point {
  const rect = element.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function normalizeBox(a: Point, b: Point) {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) };
}

function displayToSourceBox(box: { x: number; y: number; width: number; height: number }, video: HTMLVideoElement) {
  const rect = video.getBoundingClientRect();
  const naturalWidth = video.videoWidth || 1;
  const naturalHeight = video.videoHeight || 1;
  const videoAspect = naturalWidth / naturalHeight;
  const rectAspect = rect.width / rect.height;
  const drawWidth = rectAspect > videoAspect ? rect.height * videoAspect : rect.width;
  const drawHeight = rectAspect > videoAspect ? rect.height : rect.width / videoAspect;
  const offsetX = (rect.width - drawWidth) / 2;
  const offsetY = (rect.height - drawHeight) / 2;
  const x = clamp(((box.x - offsetX) / drawWidth) * naturalWidth, 0, naturalWidth);
  const y = clamp(((box.y - offsetY) / drawHeight) * naturalHeight, 0, naturalHeight);
  const width = clamp((box.width / drawWidth) * naturalWidth, 0, naturalWidth - x);
  const height = clamp((box.height / drawHeight) * naturalHeight, 0, naturalHeight - y);
  return { x, y, width, height };
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
