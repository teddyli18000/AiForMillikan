import type { CSSProperties } from "react";

export type RectLike = {
  left: number;
  top: number;
  width: number;
  height: number;
};

export type VideoDisplayMetrics = {
  sourceWidth: number;
  sourceHeight: number;
  scale: number;
  displayLeft: number;
  displayTop: number;
  displayWidth: number;
  displayHeight: number;
};

export type VideoPoint = {
  x: number;
  y: number;
};

export type VideoBox = VideoPoint & {
  width: number;
  height: number;
};

export function getContainedVideoMetrics(params: {
  videoRect: RectLike;
  overlayRect: RectLike;
  sourceWidth: number;
  sourceHeight: number;
}): VideoDisplayMetrics {
  const sourceWidth = Math.max(1, params.sourceWidth);
  const sourceHeight = Math.max(1, params.sourceHeight);
  const scale = Math.min(params.videoRect.width / sourceWidth, params.videoRect.height / sourceHeight);
  const displayWidth = sourceWidth * scale;
  const displayHeight = sourceHeight * scale;

  return {
    sourceWidth,
    sourceHeight,
    scale,
    displayLeft: params.videoRect.left - params.overlayRect.left + (params.videoRect.width - displayWidth) / 2,
    displayTop: params.videoRect.top - params.overlayRect.top + (params.videoRect.height - displayHeight) / 2,
    displayWidth,
    displayHeight
  };
}

export function clientPointToVideoPoint(
  clientX: number,
  clientY: number,
  overlayRect: RectLike,
  metrics: VideoDisplayMetrics,
  options: { clamp?: boolean } = {}
): VideoPoint | null {
  if (!Number.isFinite(metrics.scale) || metrics.scale <= 0) {
    return null;
  }

  const x = (clientX - overlayRect.left - metrics.displayLeft) / metrics.scale;
  const y = (clientY - overlayRect.top - metrics.displayTop) / metrics.scale;

  if (options.clamp) {
    return {
      x: Math.max(0, Math.min(metrics.sourceWidth, x)),
      y: Math.max(0, Math.min(metrics.sourceHeight, y))
    };
  }

  if (x < 0 || y < 0 || x > metrics.sourceWidth || y > metrics.sourceHeight) {
    return null;
  }
  return { x, y };
}

export function videoBoxToOverlayStyle(box: VideoBox, metrics: VideoDisplayMetrics): CSSProperties {
  return {
    left: `${metrics.displayLeft + box.x * metrics.scale}px`,
    top: `${metrics.displayTop + box.y * metrics.scale}px`,
    width: `${box.width * metrics.scale}px`,
    height: `${box.height * metrics.scale}px`
  };
}
