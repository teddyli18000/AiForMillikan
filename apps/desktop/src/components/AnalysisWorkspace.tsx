import { AlertTriangle, CheckCircle2, Circle, Clock3, Film, Gauge, PlayCircle } from "lucide-react";
import type { ProgressEvent, RunArtifacts } from "../types";
import { fmtCharge, fmtNumber, fmtPercent } from "../lib/format";
import { OverlayCanvas } from "./OverlayCanvas";

type AnalysisWorkspaceProps = {
  artifacts: RunArtifacts | null;
  progress: ProgressEvent | null;
  isRunning: boolean;
  onRun: () => void;
  onShowResults: () => void;
};

const stageNames = [
  "inspect video",
  "calibrate grid",
  "tracking droplets",
  "fit stable velocity segments",
  "compute charge results",
  "write visualization outputs",
  "write manifest"
];

export function AnalysisWorkspace({ artifacts, progress, isRunning, onRun, onShowResults }: AnalysisWorkspaceProps) {
  const manifest = artifacts?.manifest;
  const validity = artifacts?.validity_report;
  const elementary = artifacts?.elementary_charge_result;
  const candidates = artifacts?.tables?.candidate_tracks_summary ?? [];
  const segments = artifacts?.tables?.platform_velocity_results ?? [];
  const candidateRows: Array<Record<string, unknown>> = artifacts ? candidates.slice(0, 5) : Array.from({ length: 5 }, () => ({}));
  const segmentRows: Array<Record<string, unknown>> = artifacts ? segments.slice(0, 4) : Array.from({ length: 4 }, () => ({}));
  const percent = progress?.percent ?? (manifest ? 1 : 0);
  const activeIndex = Math.max(0, stageNames.findIndex((stage) => stage === progress?.label));

  return (
    <main className="workspace-grid">
      <aside className="status-rail glass-panel">
        <div className="panel-heading">
          <span>运行状态</span>
          <small>{fmtPercent(percent)}</small>
        </div>
        <div className="progress-ring" style={{ "--progress": percent } as React.CSSProperties}>
          <span>{Math.round(percent * 100)}</span>
        </div>
        <div className="stage-list">
          {stageNames.map((stage, index) => (
            <div key={stage} className={index < activeIndex || manifest ? "done" : index === activeIndex ? "active" : ""}>
              {index < activeIndex || manifest ? <CheckCircle2 size={16} /> : index === activeIndex ? <Clock3 size={16} /> : <Circle size={16} />}
              <span>{stage}</span>
            </div>
          ))}
        </div>
        <button className="primary-button full" disabled={isRunning} onClick={onRun}>
          <PlayCircle size={17} />
          {isRunning ? "分析中" : "开始分析"}
        </button>
        <button className="ghost-button full" disabled={!artifacts} onClick={onShowResults}>
          查看元电荷诊断
        </button>
      </aside>

      <section className="analysis-main">
        {artifacts ? <OverlayCanvas layers={artifacts.visualization_layers} /> : <AnalysisPlaceholder />}
        <div className="analysis-strip">
          <SignalCard icon={<Gauge size={18} />} label="q 计算有效" value={artifacts ? (manifest?.status?.valid_for_q ? "是" : "待验证") : "-"} tone={artifacts && manifest?.status?.valid_for_q ? "good" : undefined} />
          <SignalCard icon={<Film size={18} />} label="有效油滴数" value={artifacts ? fmtNumber(manifest?.counts?.valid_drops, 0) : "-"} />
          <SignalCard icon={<AlertTriangle size={18} />} label="元电荷诊断" value={artifacts ? elementary?.status ?? "等待运行" : "-"} tone={artifacts && elementary?.fundamental_spacing_identified ? "good" : undefined} />
          <SignalCard icon={<Gauge size={18} />} label="e_hat" value={artifacts ? fmtCharge(elementary?.elementary_charge?.e_hat_C) : "-"} />
        </div>
      </section>

      <aside className="inspector glass-panel">
        <div className="panel-heading">
          <span>有效性检查</span>
          <small>{validity?.overall_valid_for_q ? "q valid" : "pending"}</small>
        </div>
        <div className="check-list">
          {artifacts ? (validity?.checks ?? []).slice(0, 7).map((check) => (
            <div key={check.id} className={check.passed ? "check passed" : "check failed"}>
              {check.passed ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
              <span>{check.message}</span>
            </div>
          )) : Array.from({ length: 5 }, (_, index) => <div key={index} className="check"><Circle size={16} /><span>-</span></div>)}
        </div>

        <div className="panel-heading compact-heading">
          <span>候选油滴</span>
          <small>{artifacts ? `${candidates.length} rows` : "-"}</small>
        </div>
        <div className="table-wrap mini">
          <table>
            <thead>
              <tr>
                <th>rank</th>
                <th>id</th>
                <th>q</th>
              </tr>
            </thead>
            <tbody>
              {candidateRows.map((row, index) => (
                <tr key={String(row.candidate_id ?? index)}>
                  <td>{artifacts ? fmtNumber(row.rank ?? index + 1, 0) : "-"}</td>
                  <td>{artifacts ? String(row.candidate_id ?? "—") : "-"}</td>
                  <td>{artifacts ? (row.q_valid ? "valid" : "诊断") : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel-heading compact-heading">
          <span>平台拟合</span>
          <small>{artifacts ? `${segments.length} fits` : "-"}</small>
        </div>
        <div className="fit-list">
          {segmentRows.map((row, index) => (
            <div key={index}>
              <span>{artifacts ? String(row.platform_id ?? `P${index + 1}`) : "-"}</span>
              <strong>{artifacts ? `${fmtNumber(row.velocity_m_s)} m/s` : "-"}</strong>
              <small>{artifacts ? `R² ${fmtNumber(row.r2_diagnostic)}` : "-"}</small>
            </div>
          ))}
        </div>
      </aside>
    </main>
  );
}

function AnalysisPlaceholder() {
  return (
    <div className="video-stage">
      <svg viewBox="0 0 1280 720" role="img" aria-label="等待分析结果">
        <rect width="1280" height="720" fill="#03070b" />
        <text x="640" y="365" textAnchor="middle" fill="#64748b" fontSize="72">-</text>
      </svg>
      <div className="video-stage__hud"><span>-</span><strong>-</strong></div>
    </div>
  );
}

function SignalCard({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone?: "good" | "warn" }) {
  return (
    <div className={`signal-card ${tone ?? ""}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
