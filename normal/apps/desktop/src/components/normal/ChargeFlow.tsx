import type { ReactNode } from "react";
import { Activity, Calculator, CircleDot, Gauge, Ruler, Sigma } from "lucide-react";
import type { NormalRecord } from "../../types";
import { fmtCharge, fmtNumber, fmtScientific } from "../../lib/format";
import { toFiniteNumber } from "./workspaceModel";

// 数值都取自 record 的 calculation_trace，这里只负责排版。

type FlowNumbers = {
  fitTrace: Record<string, any>;
  fit: Record<string, any>;
  timeWindow: Record<string, any>;
  balanceVoltage: number | null;
  velocity: number | null;
  sigmaV: number | null;
  radius: number | null;
  etaEff: number | null;
  cunninghamLength: number | null;
  sensitivity: number | null;
  qValue: number | null;
  sigmaQ: number | null;
};

function readFlowNumbers(record: NormalRecord): FlowNumbers {
  const q = (record.q as Record<string, any> | undefined) ?? {};
  const fit = (record.fit as Record<string, any> | undefined) ?? {};
  const trace = (q.calculation_trace as Record<string, any> | undefined) ?? {};
  const fitTrace = (trace.fit as Record<string, any> | undefined) ?? {};
  const physicsTrace = (trace.physics as Record<string, any> | undefined) ?? {};
  const resultTrace = (trace.result as Record<string, any> | undefined) ?? {};
  const timeWindow = (record.time_window as Record<string, any> | undefined) ?? {};
  return {
    fitTrace,
    fit,
    timeWindow,
    radius: toFiniteNumber(physicsTrace.radius_m ?? q.radius_m ?? record.radius_m),
    velocity: toFiniteNumber(fitTrace.velocity_m_s ?? fit.velocity_m_s ?? record.fall_velocity_m_s),
    sigmaV: toFiniteNumber(fitTrace.sigma_v_m_s ?? fit.sigma_v_m_s),
    balanceVoltage: toFiniteNumber(physicsTrace.balance_voltage_V ?? q.balance_voltage_V ?? record.balance_voltage_V),
    etaEff: toFiniteNumber(physicsTrace.eta_eff_Pa_s ?? q.eta_eff_Pa_s),
    cunninghamLength: toFiniteNumber(physicsTrace.cunningham_length_m),
    sensitivity: toFiniteNumber(physicsTrace.q_velocity_sensitivity),
    qValue: toFiniteNumber(resultTrace.q_C ?? q.q_C ?? record.q_C),
    sigmaQ: toFiniteNumber(resultTrace.sigma_q_C ?? q.sigma_q_C ?? record.sigma_q_C)
  };
}

function BalanceAndWindowStep({ numbers }: { numbers: FlowNumbers }) {
  const { balanceVoltage, timeWindow } = numbers;
  return (
    <CalculationStep
      index="01"
      tone="confirmed"
      icon={<CircleDot size={18} />}
      label="用户确认"
      title="平衡与 0 V 区间"
      formula={<FormulaLine><i>U</i><sub>bal</sub>，<i>t</i><sub>0</sub> → <i>t</i><sub>1</sub></FormulaLine>}
      value={`${fmtNumber(balanceVoltage, 3)} V · ${fmtNumber(timeWindow.zero_v_start_s, 2)}–${fmtNumber(timeWindow.zero_v_end_s, 2)} s`}
    />
  );
}

function TrackAndScaleStep({ numbers }: { numbers: FlowNumbers }) {
  const { fitTrace, fit } = numbers;
  return (
    <CalculationStep
      index="02"
      tone="measured"
      icon={<Ruler size={18} />}
      label="机器测量"
      title="轨迹与标尺"
      formula={<FormulaLine><i>y</i>(<i>t</i>)，<i>s</i><sub>y</sub></FormulaLine>}
      value={`${fitTrace.fit_point_count ?? fit.fit_point_count ?? "—"} 点 · ${fmtScientific(fitTrace.scale_y_m_per_px ?? fit.scale_y_m_per_px, 3)} m/px`}
    />
  );
}

function VelocityFitStep({ numbers }: { numbers: FlowNumbers }) {
  const { velocity, sigmaV } = numbers;
  return (
    <CalculationStep
      index="03"
      tone="measured"
      icon={<Activity size={18} />}
      label="线性拟合"
      title="下落速度"
      formula={<FormulaLine><i>y</i> = <i>a</i> + <i>s t</i>，<i>v</i> = <i>s s</i><sub>y</sub></FormulaLine>}
      value={`${fmtScientific(velocity, 4)} m/s · σv ${fmtScientific(sigmaV, 3)} m/s`}
    />
  );
}

function SlipRadiusStep({ numbers }: { numbers: FlowNumbers }) {
  const { cunninghamLength, radius } = numbers;
  return (
    <CalculationStep
      index="04"
      tone="derived"
      icon={<Gauge size={18} />}
      label="物理推导"
      title="滑移修正半径"
      formula={
        <FormulaLine>
          <i>r</i> =
          <FormulaFraction
            numerator={<>√(<i>B</i><sup>2</sup> + 18<i>ηv</i>/(<i>ρg</i>)) − <i>B</i></>}
            denominator={<>2</>}
          />
        </FormulaLine>
      }
      value={`B ${fmtScientific(cunninghamLength, 3)} m · r ${fmtNumber(radius === null ? null : radius * 1e6, 4)} μm`}
    />
  );
}

function ChargeAndViscosityStep({ numbers }: { numbers: FlowNumbers }) {
  const { etaEff, qValue } = numbers;
  return (
    <CalculationStep
      index="05"
      tone="derived"
      icon={<Calculator size={18} />}
      label="物理推导"
      title="有效黏度与电荷"
      formula={
        <FormulaLine>
          <i>q</i> =
          <FormulaFraction
            numerator={<>6π<i>η</i><sub>eff</sub><i>rvd</i></>}
            denominator={<><i>U</i><sub>bal</sub></>}
          />
        </FormulaLine>
      }
      value={`ηeff ${fmtScientific(etaEff, 3)} Pa·s · q ${fmtCharge(qValue)}`}
    />
  );
}

function UncertaintyStep({ numbers }: { numbers: FlowNumbers }) {
  const { qValue, sigmaQ, sensitivity } = numbers;
  return (
    <CalculationStep
      index="06"
      tone="result"
      icon={<Sigma size={18} />}
      label="最终输出"
      title="不确定度传播"
      formula={
        <FormulaLine>
          <i>σ</i><sub>q</sub> = |<i>q</i>|
          <FormulaFraction
            numerator={<>3(<i>r</i> + <i>B</i>)</>}
            denominator={<>2<i>r</i> + <i>B</i></>}
          />
          <FormulaFraction numerator={<><i>σ</i><sub>v</sub></>} denominator={<><i>v</i></>} />
        </FormulaLine>
      }
      value={`${fmtCharge(qValue)} ± ${fmtCharge(sigmaQ)} · 灵敏度 ${fmtNumber(sensitivity, 3)}`}
    />
  );
}

export function QCalculationFlow({ record }: { record: NormalRecord }) {
  const numbers = readFlowNumbers(record);
  return (
    <section className="normal-q-flow" aria-label="单滴 q 计算流程">
      <header className="normal-q-flow__heading">
        <div>
          <strong>电荷计算过程</strong>
        </div>
      </header>
      <div className="normal-q-flow__steps">
        <BalanceAndWindowStep numbers={numbers} />
        <TrackAndScaleStep numbers={numbers} />
        <VelocityFitStep numbers={numbers} />
        <SlipRadiusStep numbers={numbers} />
        <ChargeAndViscosityStep numbers={numbers} />
        <UncertaintyStep numbers={numbers} />
      </div>
    </section>
  );
}

function CalculationStep(props: {
  index: string;
  tone: "confirmed" | "measured" | "derived" | "result";
  icon: ReactNode;
  label: string;
  title: string;
  formula: ReactNode;
  value: string;
}) {
  return (
    <article className={`normal-q-step normal-q-step--${props.tone}`}>
      <span className="normal-q-step__index">{props.index}</span>
      <div className="normal-q-step__label">{props.icon}<span>{props.label}</span></div>
      <strong>{props.title}</strong>
      {props.formula}
      <small>{props.value}</small>
    </article>
  );
}

function FormulaLine({ children }: { children: ReactNode }) {
  return <div className="normal-formula">{children}</div>;
}

function FormulaFraction({ numerator, denominator }: { numerator: ReactNode; denominator: ReactNode }) {
  return (
    <span className="normal-formula-fraction">
      <span>{numerator}</span>
      <span>{denominator}</span>
    </span>
  );
}
