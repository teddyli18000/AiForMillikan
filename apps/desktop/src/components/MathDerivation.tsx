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
        <FormulaCard title="3. 单滴物理" expression="velocity" detail={`截距 α=${fmtNumber(drop?.fit?.alpha_m_s)}；斜率 γ=${fmtNumber(drop?.fit?.gamma_m_s_V)}`} />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="4. 半径与电荷" expression="charge" detail={`q=${fmtCharge(drop?.result?.charge_abs_C)}; r=${fmtNumber(Number(drop?.result?.radius_m) * 1e6)} μm`} />
        <ArrowRight className="flow-arrow" size={18} />
        <FormulaCard title="5. 盲反演 e" expression="elementary" detail={`估计 e=${fmtCharge(e?.e_hat_C)}；不确定度=${fmtCharge(e?.sigma_e_C)}`} />
      </div>
      <div className="derivation-note">
        <FunctionSquare size={17} />
        <span>
          主估计来自固定物理区间 [1.35 × 10⁻¹⁹, 1.90 × 10⁻¹⁹] C 内的 profile likelihood 全局最大值。若元电荷间距未被识别，界面只显示为诊断候选，不宣称完成证明。
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
  const expression = {
    time: (
      <>
        <span>t</span>
        <span className="math-op">=</span>
        <span>k</span>
        <span className="math-op">/</span>
        <span>
          f<sub>s</sub>
        </span>
      </>
    ),
    fall: (
      <>
        <span>y(t)</span>
        <span className="math-op">=</span>
        <span>
          y<sub>0</sub>
        </span>
        <span className="math-op">+</span>
        <span>
          v<sub>g</sub>t
        </span>
      </>
    ),
    velocity: (
      <>
        <span>v</span>
        <span className="math-op">=</span>
        <span>α</span>
        <span className="math-op">−</span>
        <span>γU</span>
      </>
    ),
    charge: (
      <>
        <span>q</span>
        <span className="math-op">=</span>
        <span>
          6πη<sub>eff</sub>(r)
        </span>
        <span>rΔργ</span>
      </>
    ),
    elementary: (
      <>
        <span>q</span>
        <span className="math-op">=</span>
        <span>ne</span>
        <span className="math-op">+</span>
        <span>ε</span>
      </>
    )
  }[kind];
  const ariaLabel = {
    time: "time equals frame index divided by sample rate",
    fall: "vertical position equals initial position plus falling velocity times time",
    velocity: "velocity equals alpha minus gamma times voltage",
    charge: "charge equals six pi eta effective times radius times density contrast times gamma",
    elementary: "charge equals integer multiple of elementary charge plus residual"
  }[kind];
  return (
    <div className="math-expression" aria-label={ariaLabel}>
      {expression}
    </div>
  );
}
