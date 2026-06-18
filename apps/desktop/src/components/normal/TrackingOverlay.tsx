import { RefObject, useMemo } from "react";
import type { NormalBoundarySuggestion, NormalGrid, NormalRecord, NormalTarget, VideoMetadata } from "../../types";

type Props = {
  videoRef: RefObject<HTMLVideoElement | null> | ((instance: HTMLVideoElement | null) => void) | null;
  metadata: VideoMetadata | null;
  boundary: NormalBoundarySuggestion | null;
  grid: NormalGrid | null;
  target: NormalTarget | null;
  record: NormalRecord | null;
  currentTime: number;
};

export function TrackingOverlay({ videoRef, metadata, boundary, grid, target, record, currentTime }: Props) {
  const video = typeof videoRef === "function" || !videoRef ? null : videoRef.current;
  const frame = Math.round(currentTime * (metadata?.fps || 30));
  const geometry = useMemo(() => (video ? videoGeometry(video) : null), [video, video?.clientWidth, video?.clientHeight, metadata]);
  const track = ((record as unknown as { track?: Array<Record<string, unknown>> } | null)?.track) ?? [];
  const visible = track.filter((row) => Number(row.source_frame) <= frame);

  if (!geometry) return <div className="tracking-overlay" />;

  const sx = geometry.drawWidth / geometry.naturalWidth;
  const sy = geometry.drawHeight / geometry.naturalHeight;
  const toX = (x: number) => geometry.offsetX + x * sx;
  const toY = (y: number) => geometry.offsetY + y * sy;
  const points = visible.filter((row) => row.state === "tracking" || row.state === "reacquired");
  const path = points
    .map((row, index) => `${index === 0 ? "M" : "L"} ${toX(Number(row.x)).toFixed(1)} ${toY(Number(row.y)).toFixed(1)}`)
    .join(" ");
  const current = visible[visible.length - 1];

  return (
    <svg className="tracking-overlay" viewBox={`0 0 ${geometry.rectWidth} ${geometry.rectHeight}`} preserveAspectRatio="none">
      {grid?.grid_lines_y?.map((y) => (
        <line key={y} className="normal-grid-line" x1={geometry.offsetX} x2={geometry.offsetX + geometry.drawWidth} y1={toY(y)} y2={toY(y)} />
      ))}
      {grid?.second_line_y != null && <line className="normal-measure-line" x1={geometry.offsetX} x2={geometry.offsetX + geometry.drawWidth} y1={toY(grid.second_line_y)} y2={toY(grid.second_line_y)} />}
      {grid?.penultimate_line_y != null && <line className="normal-measure-line strong" x1={geometry.offsetX} x2={geometry.offsetX + geometry.drawWidth} y1={toY(grid.penultimate_line_y)} y2={toY(grid.penultimate_line_y)} />}
      {boundary && (
        <rect
          className="fit-window-band"
          x={geometry.offsetX}
          y={geometry.offsetY}
          width={geometry.drawWidth}
          height={geometry.drawHeight}
          opacity={frame >= boundary.fall_start_frame && frame <= boundary.fall_end_frame ? 0.14 : 0.04}
        />
      )}
      {target && (
        <rect
          className="target-source-box"
          x={toX(target.source_video_box.x)}
          y={toY(target.source_video_box.y)}
          width={target.source_video_box.width * sx}
          height={target.source_video_box.height * sy}
        />
      )}
      {path && <path className="track-path" d={path} />}
      {visible
        .filter((row) => row.state === "missing")
        .map((row) => <circle key={String(row.source_frame)} className="missing-point" cx={toX(Number(row.pred_x))} cy={toY(Number(row.pred_y))} r={4} />)}
      {visible
        .filter((row) => row.state === "reacquired")
        .map((row) => <circle key={String(row.source_frame)} className="reacquired-point" cx={toX(Number(row.x))} cy={toY(Number(row.y))} r={6} />)}
      {current && (
        <circle
          className={`current-point ${current.state === "missing" ? "missing" : ""}`}
          cx={toX(Number(current.state === "missing" ? current.pred_x : current.x))}
          cy={toY(Number(current.state === "missing" ? current.pred_y : current.y))}
          r={7}
        />
      )}
    </svg>
  );
}

function videoGeometry(video: HTMLVideoElement) {
  const rect = video.getBoundingClientRect();
  const naturalWidth = video.videoWidth || 1;
  const naturalHeight = video.videoHeight || 1;
  const videoAspect = naturalWidth / naturalHeight;
  const rectAspect = rect.width / rect.height;
  const drawWidth = rectAspect > videoAspect ? rect.height * videoAspect : rect.width;
  const drawHeight = rectAspect > videoAspect ? rect.height : rect.width / videoAspect;
  return { rectWidth: rect.width, rectHeight: rect.height, naturalWidth, naturalHeight, drawWidth, drawHeight, offsetX: (rect.width - drawWidth) / 2, offsetY: (rect.height - drawHeight) / 2 };
}
