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
        <FormulaCard title="1. 视频坐标" expression="time_s = frame_idx / fps" detail="+Y 向下；网格标定得到 scale_y_m_per_px" />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="2. 平台速度" expression="y(t) = a_i + v_i t" detail="在每个恒定电压平台拟合终端速度 v_i" />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="3. 单滴物理" expression="v = α - γU" detail={`α=${fmtNumber(drop?.fit?.alpha_m_s)} γ=${fmtNumber(drop?.fit?.gamma_m_s_V)}`} />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="4. 半径与电荷" expression="q = 6πη_eff(r)rdγ" detail={`q=${fmtCharge(drop?.result?.charge_abs_C)}; r=${fmtNumber(Number(drop?.result?.radius_m) * 1e6)} μm`} />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="5. 盲反演 e" expression="q_i ≈ n_i e + ε_i" detail={`e_hat=${fmtCharge(e?.e_hat_C)}; σ=${fmtCharge(e?.sigma_e_C)}`} />
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

function FormulaCard({ title, expression, detail }: { title: string; expression: string; detail: string }) {
  return (
    <div className="formula-card">
      <span>{title}</span>
      <code>{expression}</code>
      <small>{detail}</small>
    </div>
  );
}
