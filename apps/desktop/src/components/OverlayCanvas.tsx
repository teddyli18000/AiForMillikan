import type { VisualizationLayers } from "../types";

type OverlayCanvasProps = {
  layers?: VisualizationLayers;
};

type TrackPoint = {
  frame_idx?: number;
  x_px?: number;
  y_px?: number;
  valid?: boolean;
};

type TrackShape = {
  track_id?: string;
  points?: TrackPoint[];
};

export function OverlayCanvas({ layers }: OverlayCanvasProps) {
  const frame = layers?.frame ?? { width: 1280, height: 720 };
  const layerItems = layers?.layers ?? [];
  const horizontal = layerItems.find((layer) => layer.id === "horizontal_grid_lines");
  const vertical = layerItems.find((layer) => layer.id === "vertical_grid_lines");
  const rects = layerItems.filter((layer) => layer.type === "rect");
  const tracksLayer = layerItems.find((layer) => layer.id === "drop_tracks");
  const tracks = Array.isArray(tracksLayer?.tracks) ? (tracksLayer.tracks as TrackShape[]) : [];

  return (
    <div className="video-stage">
      <svg viewBox={`0 0 ${frame.width} ${frame.height}`} role="img" aria-label="实验视频诊断叠加">
        <defs>
          <radialGradient id="dropGlow">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#9bdcff" stopOpacity="0.2" />
          </radialGradient>
        </defs>
        <rect width={frame.width} height={frame.height} fill="#03070b" />
        <rect width={frame.width} height={frame.height} fill="url(#microNoise)" opacity="0.2" />
        {Array.isArray(vertical?.positions_px) &&
          vertical.positions_px.map((x, index) => (
            <line key={`v-${index}`} x1={Number(x)} x2={Number(x)} y1={80} y2={frame.height - 80} className="grid-line" />
          ))}
        {Array.isArray(horizontal?.positions_px) &&
          horizontal.positions_px.map((y, index) => (
            <line key={`h-${index}`} x1={120} x2={frame.width - 160} y1={Number(y)} y2={Number(y)} className="grid-line" />
          ))}
        {rects.map((rect) => (
          <rect
            key={rect.id}
            x={Number(rect.x ?? 0)}
            y={Number(rect.y ?? 0)}
            width={Number(rect.w ?? 0)}
            height={Number(rect.h ?? 0)}
            className={rect.id === "tracking_roi" ? "roi tracking" : "roi"}
          />
        ))}
        {tracks.map((track, index) => {
          const points: TrackPoint[] = Array.isArray(track.points) ? track.points : [];
          const path = points
            .map((point, pointIndex) => `${pointIndex === 0 ? "M" : "L"} ${Number(point.x_px)} ${Number(point.y_px)}`)
            .join(" ");
          const color = ["#3ad7ff", "#4cd964", "#ff9f0a", "#ff5ac8"][index % 4];
          const last = points[points.length - 1];
          return (
            <g key={String(track.track_id ?? index)}>
              <path d={path} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" opacity="0.86" />
              {points.map((point, pointIndex) => (
                <circle key={pointIndex} cx={Number(point.x_px)} cy={Number(point.y_px)} r={pointIndex === points.length - 1 ? 8 : 4} fill={color} />
              ))}
              {last && <circle cx={Number(last.x_px)} cy={Number(last.y_px)} r="16" fill="url(#dropGlow)" stroke={color} strokeWidth="3" />}
            </g>
          );
        })}
        <g className="axis-mark">
          <line x1="170" y1="110" x2="250" y2="110" />
          <line x1="170" y1="110" x2="170" y2="190" />
          <text x="258" y="116">+X px</text>
          <text x="142" y="205">+Y px</text>
        </g>
      </svg>
      <div className="video-stage__hud">
        <span>diagnostic_overlay.jpg / visualization_layers.json</span>
        <strong>+Y downward</strong>
      </div>
    </div>
  );
}
