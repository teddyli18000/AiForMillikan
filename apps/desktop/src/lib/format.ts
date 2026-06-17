export function fmtNumber(value: unknown, digits = 3): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  if (Math.abs(number) >= 1e4 || (number !== 0 && Math.abs(number) < 1e-3)) {
    return number.toExponential(digits);
  }
  return number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

export function fmtCharge(value: unknown): string {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${(number / 1e-19).toLocaleString("zh-CN", { maximumFractionDigits: 3 })} ×10⁻¹⁹ C`;
}

export function fmtPercent(value: unknown): string {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${Math.round(number * 100)}%`;
}

export function evidenceLabel(status?: string, supported?: boolean | null): string {
  if (supported === true) {
    return "正式支持";
  }
  if (status?.includes("insufficient")) {
    return "样本不足";
  }
  if (status?.includes("not_calibrated")) {
    return "诊断候选";
  }
  return "待验证";
}

export function classNames(...items: Array<string | false | undefined | null>): string {
  return items.filter(Boolean).join(" ");
}
