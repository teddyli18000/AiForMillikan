import type { NormalBoundarySuggestion, NormalGrid } from "../../types";

type Props = {
  boundary: NormalBoundarySuggestion;
  grid: NormalGrid | null;
  fps: number;
  onBoundary: (boundary: NormalBoundarySuggestion) => void;
  onSeek: (kind: "selection" | "start" | "end") => void;
};

export function BoundaryEditor({ boundary, grid, fps, onBoundary, onSeek }: Props) {
  const nudge = (field: "selection_frame" | "fall_start_frame" | "fall_end_frame", seconds: number) => {
    const delta = Math.round(seconds * fps);
    const next = { ...boundary, [field]: Math.max(0, Number(boundary[field]) + delta) };
    next.selection_time_s = next.selection_frame / fps;
    next.fall_start_time_s = next.fall_start_frame / fps;
    next.fall_end_time_s = next.fall_end_frame / fps;
    if (next.fall_end_frame < next.fall_start_frame) next.fall_end_frame = next.fall_start_frame;
    onBoundary(next);
  };

  return (
    <section className="normal-step-card">
      <div className="normal-step-heading">
        <span>2</span>
        <div>
          <h3>检查建议时间</h3>
          <p>先在切换前框选油滴，再只用 0V 后的下落段拟合速度。</p>
        </div>
      </div>
      <div className="boundary-grid">
        <BoundaryRow label="框选帧" frame={boundary.selection_frame} time={boundary.selection_time_s} onSeek={() => onSeek("selection")} onNudge={(s) => nudge("selection_frame", s)} />
        <BoundaryRow label="下落开始" frame={boundary.fall_start_frame} time={boundary.fall_start_time_s} onSeek={() => onSeek("start")} onNudge={(s) => nudge("fall_start_frame", s)} />
        <BoundaryRow label="下落结束" frame={boundary.fall_end_frame} time={boundary.fall_end_time_s} onSeek={() => onSeek("end")} onNudge={(s) => nudge("fall_end_frame", s)} />
      </div>
      <div className={grid?.valid ? "inline-status ok" : "inline-status warn"}>
        {grid?.valid ? `网格标定已就绪：第二条 ${grid.second_line_y}px，倒数第二条 ${grid.penultimate_line_y}px` : "网格标定需要人工复核后才能生成正式 q。"}
      </div>
    </section>
  );
}

function BoundaryRow({ label, frame, time, onSeek, onNudge }: { label: string; frame: number; time: number; onSeek: () => void; onNudge: (seconds: number) => void }) {
  return (
    <div className="boundary-row">
      <div>
        <strong>{label}</strong>
        <span>{frame} frame · {time.toFixed(2)} s</span>
      </div>
      <button className="ghost-button" onClick={onSeek}>查看</button>
      <button className="icon-button" onClick={() => onNudge(-1)}>-1</button>
      <button className="icon-button" onClick={() => onNudge(-0.1)}>-0.1</button>
      <button className="icon-button" onClick={() => onNudge(0.1)}>+0.1</button>
      <button className="icon-button" onClick={() => onNudge(1)}>+1</button>
    </div>
  );
}

