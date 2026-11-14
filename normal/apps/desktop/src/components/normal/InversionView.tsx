import { ArrowLeft, BarChart3, Download, Sigma } from "lucide-react";
import type { NormalInversionResult, NormalRecord, NormalSession } from "../../types";
import { fmtCharge, fmtPercentValue } from "../../lib/format";
import {
  diagnosticLabel,
  fixedOrDash,
  inversionStatusLabel,
  normalizeInversionCharts,
  toFiniteNumber
} from "./workspaceModel";

export function InversionPanel(props: {
  session: NormalSession | null;
  inversion: NormalInversionResult | null;
  keptValidCount: number;
  busy: boolean;
  onBackResults: () => void;
  onNextDrop: () => void;
  onExport: () => void;
  onRunInversion: () => void;
}) {
  const accepted = props.session?.counts?.kept_valid ?? props.keptValidCount;
  return (
    <div className="normal-inversion-tools">
      <div className="panel-actions">
        <button className="ghost-button" disabled={props.busy} onClick={props.onBackResults}><ArrowLeft size={15} />返回测量结果</button>
        <button className="ghost-button" disabled={props.busy} onClick={props.onExport}><Download size={15} />导出报告</button>
        <button className="ghost-button" disabled={props.busy || accepted < 3} onClick={props.onRunInversion}>重新反演</button>
        <button className="primary-button small" disabled={props.busy || !props.session?.records?.some((record) => record.status === "accepted" && record.kept)} onClick={props.onNextDrop}>下一颗油滴</button>
      </div>
      <details className="normal-inversion-options">
        <summary>搜索与诊断</summary>
        <div className="normal-inversion-settings">
          <span>搜索范围：{fmtCharge(props.inversion?.search_interval_C?.[0])} ～ {fmtCharge(props.inversion?.search_interval_C?.[1])}</span>
          <span>拟合不确定度下限：{fmtCharge(props.inversion?.sigma_floor_C)}</span>
          <span>整数分配：{props.inversion?.converged === false ? "未稳定" : "稳定"}</span>
          {(props.inversion?.flags ?? []).map((flag) => <span key={flag}>{diagnosticLabel(flag)}</span>)}
        </div>
      </details>
    </div>
  );
}

export function NormalInversionDashboard({ inversion, records }: { inversion: NormalInversionResult | null; records: NormalRecord[] }) {
  const charts = normalizeInversionCharts(inversion);
  const assignments = inversion?.assignments ?? [];
  const candidates = inversion?.candidates ?? [];
  const status = inversion?.status ?? "not_run";
  const accepted = records.filter((record) => record.status === "accepted" && record.kept);
  const comparison = inversion?.reference_comparison;
  if (!inversion) {
    return (
      <div className="normal-inversion-empty">
        <Sigma size={44} />
        <strong>等待盲反演</strong>
        <span>保留至少三条有效测量记录后，可估计元电荷。</span>
      </div>
    );
  }
  return (
    <div className="normal-inversion-dashboard" aria-label="元电荷结果页">
      <section className="normal-inversion-hero">
        <div className="normal-inversion-primary">
          <span className={`normal-inversion-status ${status === "reliable" ? "good" : status === "insufficient_eligible_records" ? "blocked" : "warn"}`}>{inversionStatusLabel(status)}</span>
          <span className="normal-inversion-eyebrow">元电荷估计</span>
          <strong className="normal-inversion-value">{fmtCharge(inversion.e_hat_C, 5)}</strong>
        </div>
        <div className="normal-inversion-kpis">
          <KpiBox label="标准不确定度 σe" value={fmtCharge(inversion.sigma_e_C, 5)} />
          <KpiBox label="相对不确定度" value={fmtPercentValue(comparison?.relative_uncertainty_percent, 3)} detail="σe / ê" />
          <KpiBox label="与标准值的相对误差" value={fmtPercentValue(comparison?.percent_error_vs_reference, 3)} detail={`参考 ${fmtCharge(comparison?.reference_e_C, 9)}`} />
          <KpiBox label="观测与拟合" value={`${inversion.valid_q_count ?? inversion.num_used ?? accepted.length} 条 · 均方根残差 ${fixedOrDash(inversion.weighted_rms, 3)}`} detail={`χ² ${fixedOrDash(inversion.chi2, 3)}`} />
        </div>
      </section>

      {status === "insufficient_eligible_records" ? (
        <section className="normal-inversion-blocker">
          <BarChart3 size={30} />
          <strong>有效 q 记录不足</strong>
          <span>当前 {inversion.valid_q_count ?? accepted.length} 条，至少需要 {inversion.min_required ?? 3} 条有效记录才能估计元电荷。</span>
        </section>
      ) : (
        <>
          <section className="normal-inversion-chart-grid">
            <ChargeAlignmentChart rows={charts.charge_distribution} levels={charts.quantized_levels} eHat={inversion.e_hat_C ?? null} />
            <ResidualChart rows={charts.residuals} />
          </section>
          <section className="normal-inversion-tables">
            <AssignmentTable assignments={assignments} records={records} />
            <CandidateList candidates={candidates} />
          </section>
        </>
      )}
    </div>
  );
}

function KpiBox({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="normal-inversion-kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function ChargeAlignmentChart({
  rows,
  levels,
  eHat
}: {
  rows: Array<{ q_C?: number; sigma_q_C?: number; n?: number; nearest_C?: number }>;
  levels: Array<{ n?: number; charge_C?: number }>;
  eHat: number | null;
}) {
  const width = 720;
  const height = 310;
  const pad = { left: 58, right: 28, top: 28, bottom: 48 };
  const values = rows.flatMap((row) => [toFiniteNumber(row.q_C), toFiniteNumber(row.nearest_C)]).filter((value): value is number => value !== null);
  const levelValues = levels.map((level) => toFiniteNumber(level.charge_C)).filter((value): value is number => value !== null);
  const all = [...values, ...levelValues, eHat ?? undefined].filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const max = all.length ? Math.max(...all) * 1.08 : 1;
  const min = 0;
  const x = (index: number) => pad.left + (rows.length <= 1 ? 0.5 : index / (rows.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => height - pad.bottom - ((value - min) / Math.max(1e-30, max - min)) * (height - pad.top - pad.bottom);
  return (
    <div className="normal-chart-panel">
      <div className="chart-heading">
        <span>q 观测与整数倍对齐</span>
        <small>误差条为 σq，横线为 nê</small>
      </div>
      <svg className="normal-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="q 观测与整数倍对齐图">
        <line className="axis strong" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <line className="axis strong" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        {levels.map((level) => {
          const value = toFiniteNumber(level.charge_C);
          if (value === null) return null;
          return (
            <g key={`level-${level.n ?? value}`}>
              <line className="normal-level-line" x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
              <text x={width - pad.right - 46} y={y(value) - 5}>n={level.n}</text>
            </g>
          );
        })}
        {rows.map((row, index) => {
          const q = toFiniteNumber(row.q_C);
          if (q === null) return null;
          const sigma = Math.max(0, toFiniteNumber(row.sigma_q_C) ?? 0);
          const cx = x(index);
          const cy = y(q);
          return (
            <g key={`q-${index}`}>
              <line className="normal-error-bar" x1={cx} x2={cx} y1={y(q - sigma)} y2={y(q + sigma)} />
              <circle className="normal-q-dot" cx={cx} cy={cy} r="6" />
              <text x={cx - 12} y={height - 26}>{index + 1}</text>
            </g>
          );
        })}
        <text x={width / 2} y={height - 4} textAnchor="middle">测量序号</text>
        <text x={12} y={26}>C</text>
      </svg>
    </div>
  );
}

function ResidualChart({ rows }: { rows: Array<{ residual_sigma?: number; n?: number; record_id?: string }> }) {
  const width = 720;
  const height = 310;
  const pad = { left: 58, right: 30, top: 32, bottom: 48 };
  const maxAbs = Math.max(2.5, ...rows.map((row) => Math.abs(toFiniteNumber(row.residual_sigma) ?? 0))) * 1.1;
  const x = (index: number) => pad.left + (rows.length <= 1 ? 0.5 : index / (rows.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + ((maxAbs - value) / (2 * maxAbs)) * (height - pad.top - pad.bottom);
  return (
    <div className="normal-chart-panel">
      <div className="chart-heading">
        <span>归一化残差</span>
        <small>残差除以有效不确定度，越接近 0 拟合越好</small>
      </div>
      <svg className="normal-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="归一化残差图">
        <line className="axis strong" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <line className="axis strong" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        {[0, 1, -1, 2, -2].map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? "normal-zero-line" : "axis faint"} x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
            <text x={18} y={y(tick) + 4}>{tick}</text>
          </g>
        ))}
        {rows.map((row, index) => {
          const residual = toFiniteNumber(row.residual_sigma) ?? 0;
          const strong = Math.abs(residual) > 2;
          return (
            <g key={`residual-${row.record_id ?? index}`}>
              <line className="normal-residual-stem" x1={x(index)} x2={x(index)} y1={y(0)} y2={y(residual)} />
              <circle className={strong ? "normal-residual-dot warn" : "normal-residual-dot"} cx={x(index)} cy={y(residual)} r="6" />
              <text x={x(index) - 10} y={height - 18}>n{row.n ?? "-"}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function CandidateList({ candidates }: { candidates: NonNullable<NormalInversionResult["candidates"]> }) {
  return (
    <div className="normal-inversion-table-card">
      <div className="chart-heading">
        <span>候选解</span>
        <small>按残差排序，保留不同整数分配</small>
      </div>
      <div className="normal-candidate-list">
        {candidates.slice(0, 6).map((candidate, index) => (
          <div key={`${candidate.e_C ?? index}-${index}`}>
            <span>#{index + 1}</span>
            <strong>{fmtCharge(candidate.e_C)}</strong>
            <small>均方根残差 {fixedOrDash(candidate.weighted_rms, 3)} · χ² {fixedOrDash(candidate.chi2, 3)}</small>
            <em>{(candidate.integer_assignment ?? []).join(" : ") || "-"}</em>
            <b>{candidate.converged ? "稳定" : "未稳定"}{candidate.boundary_hit ? " · 达到搜索边界" : ""}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssignmentTable({ assignments, records }: { assignments: NonNullable<NormalInversionResult["assignments"]>; records: NormalRecord[] }) {
  return (
    <div className="normal-inversion-table-card">
      <div className="chart-heading">
        <span>整数分配与残差</span>
        <small>各条测量记录对应的电荷数</small>
      </div>
      <div className="table-wrap normal-inversion-table">
        <table>
          <thead>
            <tr>
              <th>记录</th>
              <th>q / C</th>
              <th>n</th>
              <th>n e / C</th>
              <th>归一化残差</th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((row, index) => (
              <tr key={row.record_id ?? index}>
                <td>测量 {records.findIndex((record) => record.record_id === row.record_id) + 1}</td>
                <td>{fmtCharge(row.q_C)}</td>
                <td>{row.n ?? "-"}</td>
                <td>{fmtCharge(row.nearest_quantized_charge_C)}</td>
                <td>{fixedOrDash(row.residual_sigma, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
