import { AlertTriangle, CheckCircle2, Download, ExternalLink, FlaskConical, Gauge, ShieldCheck } from "lucide-react";
import type { RunArtifacts } from "../types";
import type { NormalElementaryEstimate, NormalQRecord } from "../types";
import { evidenceLabel, fmtCharge, fmtNumber } from "../lib/format";
import { ChargeCharts } from "./Charts";
import { MathDerivation } from "./MathDerivation";

type ResultsViewProps = {
  artifacts: RunArtifacts | null;
  normalRecords?: NormalQRecord[];
  normalElementary?: NormalElementaryEstimate | null;
  onExport: () => void;
  onOpenRun: () => void;
};

export function ResultsView({ artifacts, normalRecords = [], normalElementary, onExport, onOpenRun }: ResultsViewProps) {
  if (artifacts?.manifest?.mode === "normal_balance_fall" || artifacts?.normal_result) {
    return <NormalResultsView artifacts={artifacts} normalRecords={normalRecords} normalElementary={normalElementary} onExport={onExport} onOpenRun={onOpenRun} />;
  }
  const elementary = artifacts?.elementary_charge_result;
  const manifest = artifacts?.manifest;
  const validity = artifacts?.validity_report;
  const e = elementary?.elementary_charge;
  const comparison = artifacts?.model_comparison ?? elementary?.model_comparison ?? {};
  const supported = elementary?.fundamental_spacing_identified === true;
  const status = evidenceLabel(elementary?.status, elementary?.quantization_supported);

  return (
    <main className="results-view">
      <section className="result-hero">
        <div className="result-hero__copy">
          <span className={supported ? "status-pill success" : "status-pill warning"}>{status}</span>
          <h2>元电荷诊断</h2>
          <p>
            目标是盲反演出元电荷电荷量，并给出不确定度。界面将 bounded candidate、模型比较和有效性阻断项分开呈现。
          </p>
        </div>
        <div className="result-kpis">
          <Kpi icon={<FlaskConical size={20} />} label="估计 e" value={fmtCharge(e?.e_hat_C)} />
          <Kpi icon={<Gauge size={20} />} label="不确定度" value={fmtCharge(e?.sigma_e_C)} />
          <Kpi icon={<ShieldCheck size={20} />} label="有效油滴数" value={fmtNumber(manifest?.counts?.valid_drops ?? elementary?.num_used_drops, 0)} />
          <Kpi icon={supported ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />} label="证据强度" value={String(comparison.evidence_label ?? status)} tone={supported ? "good" : "warn"} />
        </div>
      </section>

      <section className="glass-panel conclusion-panel">
        <div className="panel-heading">
          <span>结论边界</span>
          <small>{elementary?.status ?? "等待运行"}</small>
        </div>
        <div className="conclusion-grid">
          <ConclusionItem label="q 计算有效" value={validity?.overall_valid_for_q ? "通过" : "未通过"} ok={validity?.overall_valid_for_q} />
          <ConclusionItem label="可尝试 e 估计" value={validity?.elementary_estimation_ready ? "是" : "否"} ok={validity?.elementary_estimation_ready} />
          <ConclusionItem label="有界候选" value={elementary?.bounded_estimate_available ? "存在" : "不存在"} ok={elementary?.bounded_estimate_available} />
          <ConclusionItem label="最终元电荷识别" value={supported ? "通过" : "未通过"} ok={supported} />
        </div>
        <div className="flag-row">
          {(validity?.combined_flags ?? elementary?.flags ?? ["no_run"]).map((flag) => (
            <span key={flag}>{flag}</span>
          ))}
        </div>
      </section>

      <ChargeCharts plots={artifacts?.plots_data} />
      <MathDerivation artifacts={artifacts} />

      <section className="glass-panel data-section">
        <div className="panel-heading">
          <span>逐滴 q 与不确定度</span>
          <button className="ghost-button" onClick={onOpenRun}>
            <ExternalLink size={16} />
            打开运行目录
          </button>
        </div>
        <div className="table-wrap result-table">
          <table>
            <thead>
              <tr>
                <th>drop_id</th>
                <th>track_id</th>
                <th>radius μm</th>
                <th>q / 1e-19 C</th>
                <th>σq / 1e-19 C</th>
              </tr>
            </thead>
            <tbody>
              {(artifacts?.tables?.drop_charge_results ?? []).slice(0, 12).map((row, index) => (
                <tr key={String(row.drop_id ?? index)}>
                  <td>{String(row.drop_id ?? "—")}</td>
                  <td>{String(row.track_id ?? "—")}</td>
                  <td>{fmtNumber(row.radius_um ?? Number(row.radius_m) * 1e6)}</td>
                  <td>{fmtNumber(row.charge_1e_minus_19_C ?? Number(row.charge_abs_C) / 1e-19)}</td>
                  <td>{fmtNumber(row.sigma_charge_total_1e_minus_19_C ?? Number(row.sigma_charge_total_C) / 1e-19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-actions right">
          <button className="primary-button" disabled={!artifacts?.run_dir} onClick={onExport}>
            <Download size={17} />
            导出报告
          </button>
        </div>
      </section>
    </main>
  );
}

function NormalResultsView({
  artifacts,
  normalRecords,
  normalElementary,
  onExport,
  onOpenRun
}: {
  artifacts: RunArtifacts;
  normalRecords: NormalQRecord[];
  normalElementary?: NormalElementaryEstimate | null;
  onExport: () => void;
  onOpenRun: () => void;
}) {
  const normal = artifacts.normal_result;
  const q = normal?.q_record;
  const usable = normalRecords.filter((record) => record.selected !== false && record.usable_for_inversion).length;
  return (
    <main className="results-view">
      <section className="result-hero normal-result-hero">
        <div className="result-hero__copy">
          <span className={q?.usable_for_inversion ? "status-pill success" : "status-pill warning"}>{q?.usable_for_inversion ? "q 可用" : "诊断 q"}</span>
          <h2>普通模式结果</h2>
          <p>已完成单滴平衡-下落测量。最终报告导出前，当前可用于盲反演的 q 记录数为 {usable}。</p>
        </div>
        <div className="result-kpis">
          <Kpi icon={<FlaskConical size={20} />} label="q" value={fmtCharge(q?.q_C ?? q?.result?.q_C)} />
          <Kpi icon={<Gauge size={20} />} label="sigma q" value={fmtCharge(q?.sigma_q_C ?? q?.result?.sigma_q_total_C)} />
          <Kpi icon={<ShieldCheck size={20} />} label="可用 q 数" value={fmtNumber(usable, 0)} tone={usable >= 3 ? "good" : "warn"} />
          <Kpi icon={q?.usable_for_inversion ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />} label="反演状态" value={normalElementary?.normal_algorithm?.status ?? (usable >= 3 ? "待运行" : "不足 3 条")} tone={usable >= 3 ? "good" : "warn"} />
        </div>
      </section>
      <section className="glass-panel data-section">
        <div className="panel-heading">
          <span>q 记录</span>
          <button className="ghost-button" onClick={onOpenRun}>
            <ExternalLink size={16} />
            打开运行目录
          </button>
        </div>
        <div className="table-wrap result-table">
          <table>
            <thead>
              <tr>
                <th>record</th>
                <th>q</th>
                <th>sigma</th>
                <th>usable</th>
                <th>flags</th>
              </tr>
            </thead>
            <tbody>
              {(normalRecords.length ? normalRecords : q ? [q] : []).map((record) => (
                <tr key={record.record_id}>
                  <td>{record.record_id}</td>
                  <td>{fmtCharge(record.q_C ?? record.result?.q_C)}</td>
                  <td>{fmtCharge(record.sigma_q_C ?? record.result?.sigma_q_total_C)}</td>
                  <td>{record.usable_for_inversion ? "yes" : "no"}</td>
                  <td>{(record.flags ?? []).join(", ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-actions right">
          <button className="primary-button" disabled={!artifacts?.run_dir} onClick={onExport}>
            <Download size={17} />
            导出报告
          </button>
        </div>
      </section>
      <MathDerivation artifacts={artifacts} />
    </main>
  );
}

function Kpi({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone?: "good" | "warn" }) {
  return (
    <div className={`kpi ${tone ?? ""}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ConclusionItem({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className={ok ? "conclusion ok" : "conclusion blocked"}>
      {ok ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
