import type { NormalSession } from "../../types";
import forceBalance from "../../assets/formulas/normal-force-balance.svg";
import radiusFormula from "../../assets/formulas/normal-radius.svg";
import chargeFormula from "../../assets/formulas/normal-charge.svg";

export function NormalResults({ session, onExport, onCreateQaFixture }: { session: NormalSession | null; onExport: () => void; onCreateQaFixture: () => void }) {
  if (!session?.inversion && !session?.eligible_for_inversion) return null;
  const inversion = session.inversion as Record<string, any> | undefined;
  return (
    <section className="normal-step-card normal-results">
      <div className="normal-step-heading">
        <span>反演</span>
        <div>
          <h3>盲反演结果</h3>
          <p>仅使用当前选中的有效 q。QA fixture 会明确标记，不作为真实视频证据。</p>
        </div>
      </div>
      <div className="formula-strip" aria-label="普通模式公式">
        <img src={forceBalance} alt="平衡阶段 q U balance divided by d equals m g" />
        <img src={radiusFormula} alt="Cunningham 修正半径正根公式" />
        <img src={chargeFormula} alt="由半径和平衡电压计算 q 的公式" />
      </div>
      {!session.eligible_for_inversion && (
        <div className="inline-status warn">
          至少需要 3 条已选有效 q。可继续真实测量；如只验证界面，可创建 QA fixture session。
          <button className="ghost-button" onClick={onCreateQaFixture}>创建 QA fixture session</button>
        </div>
      )}
      {inversion && (
        <div className="inversion-grid">
          <ResultCard title="普通算法" value={formatE(inversion.normal?.e_hat_C)} status={String(inversion.normal?.status ?? "-")} />
          <ResultCard title="Experimental adapter" value={formatE(inversion.experimental?.result?.elementary_charge?.e_hat_C)} status={String(inversion.experimental?.status ?? "-")} />
        </div>
      )}
      <button className="primary-button" onClick={onExport}>生成并导出报告包</button>
    </section>
  );
}

function ResultCard({ title, value, status }: { title: string; value: string; status: string }) {
  return (
    <div className="inversion-card">
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{status}</small>
    </div>
  );
}

function formatE(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n / 1e-19).toFixed(4)} × 10^-19 C` : "-";
}
