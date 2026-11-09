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
        <OverlayCanvas layers={artifacts?.visualization_layers} />
        <div className="analysis-strip">
          <SignalCard icon={<Gauge size={18} />} label="q 计算有效" value={manifest?.status?.valid_for_q ? "是" : "待验证"} tone={manifest?.status?.valid_for_q ? "good" : "warn"} />
          <SignalCard icon={<Film size={18} />} label="有效油滴数" value={fmtNumber(manifest?.counts?.valid_drops, 0)} />
          <SignalCard icon={<AlertTriangle size={18} />} label="元电荷诊断" value={elementary?.status ?? "等待运行"} tone={elementary?.fundamental_spacing_identified ? "good" : "warn"} />
          <SignalCard icon={<Gauge size={18} />} label="e_hat" value={fmtCharge(elementary?.elementary_charge?.e_hat_C)} />
        </div>
      </section>

      <aside className="inspector glass-panel">
        <div className="panel-heading">
          <span>有效性检查</span>
          <small>{validity?.overall_valid_for_q ? "q valid" : "pending"}</small>
        </div>
        <div className="check-list">
          {(validity?.checks ?? []).slice(0, 7).map((check) => (
            <div key={check.id} className={check.passed ? "check passed" : "check failed"}>
              {check.passed ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
              <span>{check.message}</span>
            </div>
          ))}
        </div>

        <div className="panel-heading compact-heading">
          <span>候选油滴</span>
          <small>{candidates.length} rows</small>
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
              {candidates.slice(0, 5).map((row, index) => (
                <tr key={String(row.candidate_id ?? index)}>
                  <td>{fmtNumber(row.rank ?? index + 1, 0)}</td>
                  <td>{String(row.candidate_id ?? "—")}</td>
                  <td>{row.q_valid ? "valid" : "诊断"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel-heading compact-heading">
          <span>平台拟合</span>
          <small>{segments.length} fits</small>
        </div>
        <div className="fit-list">
          {segments.slice(0, 4).map((row, index) => (
            <div key={index}>
              <span>{String(row.platform_id ?? `P${index + 1}`)}</span>
              <strong>{fmtNumber(row.velocity_m_s)} m/s</strong>
              <small>R² {fmtNumber(row.r2_diagnostic)}</small>
            </div>
          ))}
        </div>
      </aside>
    </main>
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
