import { ArrowRight, FunctionSquare, Sigma } from "lucide-react";
import type { RunArtifacts } from "../types";
import { fmtCharge, fmtNumber } from "../lib/format";

type MathDerivationProps = {
  artifacts?: RunArtifacts | null;
};

export function MathDerivation({ artifacts }: MathDerivationProps) {
  const elementary = artifacts?.elementary_charge_result;
  const drop = artifacts?.drop_results as { fit?: Record<string, unknown>; result?: Record<string, unknown> } | undefined;
  const e = elementary?.elementary_charge;
  return (
    <section className="math-panel">
      <div className="math-header">
        <div>
          <span>数学推导</span>
          <strong>从视频轨迹到元电荷盲反演</strong>
        </div>
        <Sigma size={24} />
      </div>
      <div className="derivation-flow">
        <FormulaCard title="1. 视频坐标" expression="time" detail="+Y 向下；网格标定得到纵向比例尺" />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="2. 下落速度" expression="fall" detail="普通模式只使用真实 tracking 点拟合 0V 下落速度" />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="3. 单滴物理" expression="velocity" detail={`alpha=${fmtNumber(drop?.fit?.alpha_m_s)} gamma=${fmtNumber(drop?.fit?.gamma_m_s_V)}`} />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="4. 半径与电荷" expression="charge" detail={`q=${fmtCharge(drop?.result?.charge_abs_C)}; r=${fmtNumber(Number(drop?.result?.radius_m) * 1e6)} μm`} />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="5. 盲反演 e" expression="elementary" detail={`e=${fmtCharge(e?.e_hat_C)}; sigma=${fmtCharge(e?.sigma_e_C)}`} />
      </div>
      <div className="derivation-note">
        <FunctionSquare size={17} />
        <span>
          主估计来自固定物理区间 [1.35e-19, 1.90e-19] C 内的 profile likelihood 全局最大值。若
          fundamental_spacing_identified=false，界面只显示为诊断候选，不宣称完成证明。
        </span>
      </div>
    </section>
  );
}

function FormulaCard({ title, expression, detail }: { title: string; expression: "time" | "fall" | "velocity" | "charge" | "elementary"; detail: string }) {
  return (
    <div className="formula-card">
      <span>{title}</span>
      <MathExpression kind={expression} />
      <small>{detail}</small>
    </div>
  );
}

function MathExpression({ kind }: { kind: "time" | "fall" | "velocity" | "charge" | "elementary" }) {
  const labels = {
    time: ["t", "=", "k", "/", "f_s"],
    fall: ["y(t)", "=", "y_0", "+", "v_g t"],
    velocity: ["v", "=", "α", "−", "γ U"],
    charge: ["q", "=", "6π", "η_eff(r)", "r d γ"],
    elementary: ["q", "=", "n e", "+", "ε"]
  }[kind];
  return (
    <div className="math-expression" aria-label={labels.join(" ")}>
      {labels.map((label, index) => (
        <span key={`${label}-${index}`} className={index % 2 === 1 ? "math-op" : ""}>
          {label}
        </span>
      ))}
    </div>
  );
}
