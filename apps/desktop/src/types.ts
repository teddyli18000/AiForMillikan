export type VideoMetadata = {
  path: string;
  readable: boolean;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration_s: number;
};

export type ManualPlatform = {
  platform_id?: string;
  start_frame: number;
  end_frame: number;
  start_time_s?: number;
  end_time_s?: number;
  voltage_V: number;
  voltage_confidence?: number;
  source?: string;
};

export type ProgressEvent = {
  percent: number;
  label: string;
};

export type NormalProgressEvent = {
  request_id: string;
  operation: string;
  stage: string;
  label: string;
  current?: number | null;
  total?: number | null;
  unit?: string | null;
  fraction?: number | null;
  indeterminate: boolean;
};

export type StatusMap = {
  video_readable?: boolean;
  valid_for_q?: boolean;
  valid_for_elementary_charge?: boolean;
  elementary_estimation_ready?: boolean;
  bounded_estimate_available?: boolean;
  quantization_supported?: boolean | null;
  elementary_status?: string;
  flags?: string[];
};

export type RunManifest = {
  schema_version?: number;
  run_dir?: string;
  status?: StatusMap;
  counts?: Record<string, number>;
  coordinate_system?: Record<string, string>;
  video?: Partial<VideoMetadata>;
  visualizations?: Record<string, string>;
  primary_results?: Record<string, unknown>;
  files?: Record<string, string>;
};

export type ValidityCheck = {
  id: string;
  passed: boolean;
  message: string;
  details?: Record<string, unknown>;
};

export type ValidityReport = {
  overall_valid_for_q?: boolean;
  overall_valid_for_elementary_charge?: boolean;
  elementary_estimation_ready?: boolean;
  bounded_estimate_available?: boolean;
  quantization_supported?: boolean | null;
  elementary_status?: string;
  blocking_failed_checks?: string[];
  combined_flags?: string[];
  checks?: ValidityCheck[];
};

export type ElementaryResult = {
  valid?: boolean;
  fit_valid?: boolean;
  bounded_estimate_available?: boolean;
  quantization_favored?: boolean;
  quantization_supported?: boolean | null;
  fundamental_spacing_identified?: boolean;
  primitive_assignment_supported?: boolean;
  status?: string;
  reason?: string;
  flags?: string[];
  num_used_drops?: number;
  elementary_charge?: {
    e_hat_C?: number | null;
    sigma_e_C?: number | null;
    ci_95_C?: [number, number] | null;
    profile_ci_95_C?: [number, number] | null;
    search_interval_C?: [number, number];
  };
  drops?: Array<Record<string, unknown>>;
  model_comparison?: Record<string, unknown>;
};

export type PlotPoint = Record<string, number | string | boolean | null | undefined>;

export type PlotsData = {
  schema_version?: number;
  status?: string;
  reason?: string;
  summary?: Record<string, unknown>;
  charts?: {
    charge_distribution?: {
      observations?: PlotPoint[];
      quantized_density?: PlotPoint[];
      continuous_density?: PlotPoint[];
      quantized_levels?: PlotPoint[];
    };
    integer_assignment?: {
      points?: PlotPoint[];
    };
    phase_residual?: {
      points?: PlotPoint[];
      histogram?: PlotPoint[];
    };
    model_comparison?: {
      per_drop?: PlotPoint[];
      delta_elpd?: number;
      quantized_elpd?: number;
      continuous_elpd?: number;
      status?: string;
    };
  };
};

export type VisualizationLayer = {
  id: string;
  type: string;
  label?: string;
  [key: string]: unknown;
};

export type VisualizationLayers = {
  schema_version?: number;
  frame?: {
    width: number;
    height: number;
    fps: number;
    frame_count: number;
    duration_s: number;
  };
  coordinate_system?: Record<string, string>;
  layers?: VisualizationLayer[];
};

export type RunArtifacts = {
  run_dir?: string;
  manifest?: RunManifest;
  summary?: string;
  analysis_report_md?: string;
  diagnostics?: Record<string, unknown>;
  validity_report?: ValidityReport;
  visualization_layers?: VisualizationLayers;
  drop_results?: Record<string, unknown>;
  multi_drop_results?: Record<string, unknown>;
  elementary_charge_result?: ElementaryResult;
  model_comparison?: Record<string, unknown>;
  uncertainty_details?: Record<string, unknown>;
  quality_scores?: Record<string, unknown>;
  plots_data?: PlotsData;
  tables?: {
    platforms?: Array<Record<string, unknown>>;
    auto_platform_suggestions?: Array<Record<string, unknown>>;
    candidate_tracks_summary?: Array<Record<string, unknown>>;
    best_track_segments?: Array<Record<string, unknown>>;
    drop_track_segments?: Array<Record<string, unknown>>;
    drop_charge_results?: Array<Record<string, unknown>>;
    platform_velocity_results?: Array<Record<string, unknown>>;
    trajectory_quality_scores?: Array<Record<string, unknown>>;
  };
};

export type AnalysisResponse = {
  run_dir: string;
  config_path?: string;
  manifest?: RunManifest;
  validation_errors?: string[];
  artifacts?: RunArtifacts;
};

export type AppMode = "normal" | "experimental";

export type NormalBoundary = {
  zero_v_start_s: number;
  zero_v_end_s: number;
  zero_v_start_frame?: number;
  zero_v_end_frame?: number;
  selection_time_s?: number;
  selection_frame?: number;
  source?: string;
  flags?: string[];
};

export type NormalGrid = {
  line_y_px?: number[];
  effective_top_px?: number | null;
  effective_bottom_px?: number | null;
  scale_y_m_per_px?: number | null;
  measurement_distance_m?: number | null;
  flags?: string[];
  [key: string]: unknown;
};

export type NormalCrossingEvent = {
  event_id: string;
  grid_line_y_px?: number;
  frame_idx?: number;
  start_time_s?: number;
  end_time_s?: number;
  time_s?: number;
  review_start_time_s?: number;
  review_end_time_s?: number;
  review_result?: "same_drop" | "different_drop";
  review_clip_url?: string;
  review_clip_path?: string;
  source_video_box?: { x: number; y: number; width: number; height: number };
  [key: string]: unknown;
};

export type NormalRecord = {
  record_id: string;
  video_path?: string;
  kept: boolean;
  valid: boolean;
  q_valid?: boolean;
  status?: string;
  q_C?: number | null;
  sigma_q_C?: number | null;
  radius_m?: number | null;
  fall_velocity_m_s?: number | null;
  balance_voltage_V?: number | null;
  flags?: string[];
  artifacts?: Record<string, string>;
  crossings?: NormalCrossingEvent[];
  [key: string]: unknown;
};

export type NormalSession = {
  session_root: string;
  records: NormalRecord[];
  active_video?: Record<string, unknown> | null;
  counts?: {
    total?: number;
    valid?: number;
    kept_valid?: number;
    selected_valid?: number;
  };
  inversion?: NormalInversionResult | null;
  [key: string]: unknown;
};

export type NormalInitializeResponse = {
  session: NormalSession;
  session_root: string;
  run_root: string;
  session_file?: string;
  config: Record<string, any>;
};

export type NormalInspectVideoResponse = {
  video_path: string;
  video_url: string;
  metadata: VideoMetadata;
};

export type NormalPrepareVideoResponse = {
  session_root: string;
  video_path: string;
  video_url?: string;
  metadata: VideoMetadata;
  boundary: NormalBoundary & {
    confidence?: number;
    diagnostics?: Record<string, unknown>;
  };
  boundary_diagnostics?: Record<string, unknown>;
  grid: NormalGrid;
  session: NormalSession;
  config: Record<string, any>;
};

export type NormalStateResponse = {
  session_root: string;
  active_video?: Record<string, unknown>;
  session: NormalSession;
};

export type NormalMeasurementResponse = {
  session_root: string;
  record: NormalRecord;
  session: NormalSession;
};

export type NormalInversionResult = {
  status?: string;
  e_hat_C?: number | null;
  sigma_e_C?: number | null;
  valid_q_count?: number;
  quantized?: Record<string, unknown>;
  continuous?: Record<string, unknown>;
  comparison?: Record<string, unknown>;
  assignments?: Array<Record<string, unknown>>;
  plots_data?: Record<string, unknown>;
  flags?: string[];
  [key: string]: unknown;
};

export type NormalInversionResponse = {
  session_root: string;
  inversion: NormalInversionResult;
  session: NormalSession;
};

export type NormalCrossingReviewResponse = {
  session_root: string;
  record: NormalRecord;
  event?: NormalCrossingEvent;
  session: NormalSession;
};

export type DesktopApi = {
  openVideoDialog: () => Promise<string | null>;
  openRunDialog: () => Promise<string | null>;
  inspectVideo: (payload: { video_path: string }) => Promise<{ metadata: VideoMetadata }>;
  detectPlatformBoundaries: (payload: {
    video_path: string;
    config_path?: string;
    expected_platform_count: number;
  }) => Promise<{ diagnostics: Record<string, unknown>; suggestions: Array<Record<string, unknown>>; samples: Array<Record<string, unknown>> }>;
  runAnalysis: (payload: {
    video_path: string;
    config_path?: string;
    run_dir?: string;
    manual_platforms?: ManualPlatform[];
  }) => Promise<AnalysisResponse>;
  runAutoAnalysis: (payload: {
    video_path: string;
    config_path?: string;
    run_dir?: string;
    expected_platform_count: number;
    platform_values: number[];
  }) => Promise<AnalysisResponse>;
  loadRun: (payload: { run_dir: string }) => Promise<{ artifacts: RunArtifacts }>;
  validateRun: (payload: { run_dir: string; config_path?: string }) => Promise<{ valid: boolean; errors: string[] }>;
  runDownstream: (payload: unknown) => Promise<unknown>;
  exportReport: (payload: { run_dir: string; include_pdf?: boolean; mode?: "folder" | "zip" }) => Promise<unknown>;
  getDroppedFilePath: (file: File) => Promise<string>;
  normalInitialize: (payload?: { session_root?: string; run_root?: string; config_overrides?: Record<string, unknown> }) => Promise<NormalInitializeResponse>;
  normalInspectVideo: (payload: { video_path: string }) => Promise<NormalInspectVideoResponse>;
  normalPrepareVideo: (payload: {
    video_path: string;
    session_root?: string;
    run_root?: string;
    config_overrides?: Record<string, unknown>;
  }) => Promise<NormalPrepareVideoResponse>;
  normalConfirmBoundary: (payload: { session_root?: string; boundary: NormalBoundary }) => Promise<NormalStateResponse>;
  normalSelectTarget: (payload: Record<string, unknown>) => Promise<NormalStateResponse>;
  normalSaveMeasurement: (payload: Record<string, unknown>) => Promise<NormalMeasurementResponse>;
  normalPrepareCrossingReview: (payload: { session_root?: string; record_id: string; event_id: string }) => Promise<NormalCrossingReviewResponse>;
  normalReviewCrossing: (payload: { session_root?: string; record_id: string; event_id: string; result: "same_drop" | "different_drop" }) => Promise<NormalCrossingReviewResponse>;
  normalSelectRecord: (payload: { session_root?: string; record_id: string; kept: boolean }) => Promise<NormalSession>;
  normalRunInversion: (payload?: { session_root?: string; config_overrides?: Record<string, unknown> }) => Promise<NormalInversionResponse>;
  normalExportSession: (payload?: { session_root?: string }) => Promise<unknown>;
  openPath: (targetPath: string) => Promise<unknown>;
  onAnalysisProgress: (callback: (progress: ProgressEvent) => void) => () => void;
  onNormalProgress: (callback: (progress: NormalProgressEvent) => void) => () => void;
};
