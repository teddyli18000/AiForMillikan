import type { PlotPoint, PlotsData } from "../types";
import { fmtCharge, fmtNumber } from "../lib/format";

type ChartsProps = {
  plots?: PlotsData;
};

export function ChargeCharts({ plots }: ChartsProps) {
  const charge = plots?.charts?.charge_distribution;
  const assignment = plots?.charts?.integer_assignment;
  const phase = plots?.charts?.phase_residual;
  const comparison = plots?.charts?.model_comparison;

  return (
    <div className="chart-grid">
      <ChartPanel title="电荷分布" subtitle="观测电荷与量子化/连续预测密度">
        <DensityChart observations={charge?.observations ?? []} quantized={charge?.quantized_density ?? []} continuous={charge?.continuous_density ?? []} />
      </ChartPanel>
      <ChartPanel title="整数倍归属" subtitle="观测电荷到整数倍归属">
        <AssignmentChart points={assignment?.points ?? []} />
      </ChartPanel>
      <ChartPanel title="相位残差" subtitle="电荷除以候选元电荷后的余量">
        <PhaseChart points={phase?.points ?? []} />
      </ChartPanel>
      <ChartPanel title="模型比较" subtitle="逐滴 predictive density 差值">
        <ModelComparisonChart points={comparison?.per_drop ?? []} delta={comparison?.delta_elpd} />
      </ChartPanel>
    </div>
  );
}

function ChartPanel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="chart-panel">
      <div className="chart-heading">
        <span>{title}</span>
        <small>{subtitle}</small>
      </div>
      {children}
    </section>
  );
}

function DensityChart({ observations, quantized, continuous }: { observations: PlotPoint[]; quantized: PlotPoint[]; continuous: PlotPoint[] }) {
  const xs = [...observations.map((point) => Number(point.q_C)), ...quantized.map((point) => Number(point.q_C)), ...continuous.map((point) => Number(point.q_C))].filter(Number.isFinite);
  const min = Math.min(...xs, 1e-19);
  const max = Math.max(...xs, 10e-19);
  const x = (value: number) => 36 + ((value - min) / Math.max(max - min, 1e-30)) * 300;
  const qPath = buildPath(quantized, x, "#", "density", 118);
  const cPath = buildPath(continuous, x, "#", "density", 118);
  return (
    <svg className="chart-svg" viewBox="0 0 380 170">
      <line x1="34" x2="350" y1="132" y2="132" className="axis" />
      <path d={cPath} className="density continuous" />
      <path d={qPath} className="density quantized" />
      {observations.map((point, index) => (
        <g key={String(point.drop_id ?? index)}>
          <circle cx={x(Number(point.q_C))} cy={128 - (index % 4) * 11} r="5" className="observation" />
          <title>{`${point.drop_id}: ${fmtCharge(point.q_C)}`}</title>
        </g>
      ))}
      <text x="36" y="154">{fmtCharge(min)}</text>
      <text x="250" y="154">{fmtCharge(max)}</text>
    </svg>
  );
}

function AssignmentChart({ points }: { points: PlotPoint[] }) {
  const maxN = Math.max(...points.map((point) => Number(point.n_hat)).filter(Number.isFinite), 8);
  const x = (n: number) => 34 + (n / Math.max(1, maxN)) * 300;
  return (
    <svg className="chart-svg" viewBox="0 0 380 170">
      <line x1="34" x2="350" y1="132" y2="132" className="axis" />
      {points.map((point, index) => {
        const n = Number(point.n_hat);
        const residual = Number(point.normalized_residual ?? 0);
        return (
          <g key={String(point.drop_id ?? index)}>
            <line x1={x(n)} x2={x(n)} y1="48" y2="132" className="comb" />
            <circle cx={x(n)} cy={90 - residual * 32} r="6" className="assignment-dot" />
            <title>{`${point.drop_id}: n=${n}, residual=${fmtNumber(residual)}`}</title>
          </g>
        );
      })}
      <text x="34" y="154">n=0</text>
      <text x="300" y="154">n={maxN}</text>
    </svg>
  );
}

function PhaseChart({ points }: { points: PlotPoint[] }) {
  const x = (index: number) => 42 + (index / Math.max(1, points.length - 1)) * 290;
  const y = (phase: number) => 84 - phase * 110;
  return (
    <svg className="chart-svg" viewBox="0 0 380 170">
      <line x1="34" x2="350" y1="84" y2="84" className="axis strong" />
      <line x1="34" x2="350" y1="29" y2="29" className="axis faint" />
      <line x1="34" x2="350" y1="139" y2="139" className="axis faint" />
      {points.map((point, index) => {
        const phase = Number(point.phase_residual ?? 0);
        return <circle key={String(point.drop_id ?? index)} cx={x(index)} cy={y(phase)} r="6" className="phase-dot" />;
      })}
      <text x="34" y="24">+0.5</text>
      <text x="34" y="158">-0.5</text>
    </svg>
  );
}

function ModelComparisonChart({ points, delta }: { points: PlotPoint[]; delta?: number }) {
  const maxAbs = Math.max(...points.map((point) => Math.abs(Number(point.delta_log_predictive_density))).filter(Number.isFinite), 1);
  return (
    <svg className="chart-svg" viewBox="0 0 380 170">
      <line x1="36" x2="350" y1="88" y2="88" className="axis strong" />
      {points.map((point, index) => {
        const value = Number(point.delta_log_predictive_density ?? 0);
        const width = Math.abs(value / maxAbs) * 120;
        const y = 35 + index * (96 / Math.max(1, points.length - 1));
        return (
          <rect
            key={String(point.drop_id ?? index)}
            x={value >= 0 ? 190 : 190 - width}
            y={y}
            width={width}
            height="9"
            rx="4"
            className={value >= 0 ? "bar-positive" : "bar-negative"}
          />
        );
      })}
      <text x="36" y="154">Delta ELPD {fmtNumber(delta)}</text>
    </svg>
  );
}

function buildPath(points: PlotPoint[], x: (value: number) => number, _unused: string, valueKey: string, baseline: number): string {
  if (!points.length) {
    return "";
  }
  const maxDensity = Math.max(...points.map((point) => Number(point[valueKey])).filter(Number.isFinite), 1);
  return points
    .map((point, index) => {
      const px = x(Number(point.q_C));
      const py = baseline - (Number(point[valueKey]) / maxDensity) * 82;
      return `${index === 0 ? "M" : "L"} ${px.toFixed(2)} ${py.toFixed(2)}`;
    })
    .join(" ");
}
