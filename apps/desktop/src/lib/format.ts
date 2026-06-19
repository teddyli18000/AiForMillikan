const superscriptDigits: Record<string, string> = {
  "-": "⁻",
  "+": "⁺",
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹"
};

function superscript(value: number): string {
  return String(value)
    .split("")
    .map((character) => superscriptDigits[character] ?? character)
    .join("");
}

function decimal(value: number, digits: number): string {
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
    useGrouping: false
  });
}

export function fmtScientific(value: unknown, digits = 3, fixedExponent?: number): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  if (number === 0) {
    return "0";
  }
  const exponent = fixedExponent ?? Math.floor(Math.log10(Math.abs(number)));
  const coefficient = number / 10 ** exponent;
  return `${decimal(coefficient, digits)} × 10${superscript(exponent)}`;
}

export function fmtNumber(value: unknown, digits = 3): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  if (Math.abs(number) >= 1e4 || (number !== 0 && Math.abs(number) < 1e-3)) {
    return fmtScientific(number, digits);
  }
  return number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

export function fmtCharge(value: unknown, digits = 4): string {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${fmtScientific(number, digits, -19)} C`;
}

export function fmtPercent(value: unknown): string {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${Math.round(number * 100)}%`;
}

export function fmtPercentValue(value: unknown, digits = 2): string {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${decimal(number, digits)}%`;
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
