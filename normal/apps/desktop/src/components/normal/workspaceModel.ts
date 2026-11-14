import type { NormalBoundary, NormalInversionResult, VideoMetadata } from "../../types";

// 面板和主工作区都从这儿取格式、时间窗和状态词，别把 IPC 调用塞进来。

export type MeasurementStage = "import" | "boundary" | "target" | "review" | "results" | "inversion";

export const stageSteps: Array<{ id: MeasurementStage; title: string }> = [
  { id: "import", title: "导入视频" },
  { id: "boundary", title: "确认零电压区间" },
  { id: "target", title: "框选油滴" },
  { id: "review", title: "复核轨迹" },
  { id: "results", title: "测量结果" },
  { id: "inversion", title: "元电荷估计" }
];

export const parameterLabels: Record<string, string> = {
  plate_distance_m: "极板间距（m）",
  air_viscosity_Pa_s: "空气黏度（Pa·s）",
  pressure_kPa: "气压（kPa）",
  oil_density_kg_m3: "油滴密度（kg/m³）",
  cunningham_b_kPa_m: "滑移修正系数（kPa·m）",
  gravity_m_s2: "重力加速度（m/s²）",
  measurement_distance_m: "测量距离（m）"
};

export const diagnosticLabels: Record<string, string> = {
  zero_v_operation_not_detected: "未识别到零电压切换，请手动调整区间",
  zero_v_end_needs_review: "请确认零电压结束时间",
  insufficient_eligible_records: "有效记录不足三条",
  weighted_residual_too_large: "拟合残差较大",
  integer_assignments_nonprimitive: "整数分配存在公因数",
  search_boundary_hit: "结果位于搜索边界",
  integer_assignment_not_stable: "整数分配尚未稳定",
  exploratory_small_sample: "样本较少，结果供参考"
};

export const diagnosticLabel = (flag: string) => diagnosticLabels[flag] ?? "结果需复核";

export const physicsParameterKeys = [
  "plate_distance_m",
  "air_viscosity_Pa_s",
  "pressure_kPa",
  "oil_density_kg_m3",
  "cunningham_b_kPa_m",
  "gravity_m_s2"
];

export const gridParameterKeys = ["measurement_distance_m"];

export const fixedOrDash = (value?: number | null, digits = 2) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(digits);
};

export const recordStatusLabel = (status?: string) => {
  const labels: Record<string, string> = {
    pending_crossing_review: "待轨迹复核",
    pending_user_confirmation: "待用户确认",
    accepted: "已保留",
    diagnostic: "诊断",
    rejected_crossing_identity: "油滴不一致",
    rejected_by_user: "已排除"
  };
  return labels[status || ""] || "未开始";
};

export function clampBoundary(boundary: NormalBoundary, metadata: VideoMetadata | null, options: { preserveSelectionWindow?: boolean } = {}): NormalBoundary {
  const duration = metadata?.duration_s && Number.isFinite(metadata.duration_s) ? metadata.duration_s : Number.POSITIVE_INFINITY;
  const start = Math.max(0, Math.min(Number(boundary.zero_v_start_s || 0), duration));
  const end = Math.max(start, Math.min(Number(boundary.zero_v_end_s || 0), duration));
  const clamped: NormalBoundary = { ...boundary, zero_v_start_s: Number(start.toFixed(3)), zero_v_end_s: Number(end.toFixed(3)), source: "manual_ui" };
  if (!options.preserveSelectionWindow) {
    delete clamped.selection_window;
    delete clamped.selection_time_s;
    delete clamped.selection_frame;
    delete clamped.zero_v_start_frame;
    delete clamped.zero_v_end_frame;
  }
  return clamped;
}

export function selectionWindowFromBoundary(boundary: NormalBoundary, metadata: VideoMetadata | null) {
  const duration = metadata?.duration_s && Number.isFinite(metadata.duration_s) ? metadata.duration_s : Number.POSITIVE_INFINITY;
  const configured = boundary.selection_window;
  const start = configured?.start_s ?? Math.max(0, Number(boundary.zero_v_start_s || 0) - 0.5);
  const end = configured?.end_s ?? Math.min(duration, Number(boundary.zero_v_start_s || 0) + 0.5);
  const safeStart = Math.max(0, Math.min(start, duration));
  const safeEnd = Math.max(safeStart, Math.min(end, duration));
  return { start_s: Number(safeStart.toFixed(3)), end_s: Number(safeEnd.toFixed(3)), source: configured?.source ?? "normal_v1_default" };
}

export function clampSelectionTime(time: number, boundary: NormalBoundary, metadata: VideoMetadata | null) {
  const selectionRange = selectionWindowFromBoundary(boundary, metadata);
  return Number(Math.max(selectionRange.start_s, Math.min(selectionRange.end_s, time)).toFixed(3));
}

export function normalizeInversionCharts(inversion: NormalInversionResult | null) {
  const raw = (inversion?.charts ?? {}) as Record<string, any>;
  return {
    charge_distribution: Array.isArray(raw.charge_distribution) ? raw.charge_distribution : [],
    residuals: Array.isArray(raw.residuals) ? raw.residuals : [],
    quantized_levels: Array.isArray(raw.quantized_levels) ? raw.quantized_levels : []
  };
}

export function toFiniteNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function inversionStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    reliable: "可靠候选",
    exploratory: "探索性结果",
    diagnostic: "诊断结果",
    insufficient_eligible_records: "记录不足",
    ok: "探索性结果",
    not_run: "未运行"
  };
  return labels[status || ""] ?? "未运行";
}

// 后端按 physics / grid 分组回传覆盖值，表单里却是扁平的，恢复记录时摊平一次就够了。
export function flatParameterOverrides(overrides: Record<string, unknown> = {}) {
  return Object.fromEntries(
    Object.entries(overrides).flatMap(([group, value]) =>
      value && typeof value === "object" && !Array.isArray(value)
        ? Object.entries(value as Record<string, unknown>).map(([key, nested]) => [key, String(nested)])
        : [[group, String(value)]]
    )
  );
}
