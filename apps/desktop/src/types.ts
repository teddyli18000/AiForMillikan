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

export type StartupCheck = {
  id: string;
  label: string;
  ok: boolean;
  detail?: string;
};

export type AppInitialization = {
  ok: boolean;
  checks: StartupCheck[];
  runtime?: Record<string, string>;
  worker?: unknown;
};

export type NormalBoundarySuggestion = {
  selection_frame: number;
  selection_time_s: number;
  fall_start_frame: number;
  fall_start_time_s: number;
  fall_end_frame: number;
  fall_end_time_s: number;
  end_source: string;
  flags?: string[];
};

export type NormalGrid = {
  valid: boolean;
  grid_lines_y?: number[];
  second_line_y?: number;
  penultimate_line_y?: number;
  scale_y_m_per_px?: number;
  warnings?: string[];
};

export type NormalTarget = {
  display_box: { x: number; y: number; width: number; height: number };
  source_video_box: { x: number; y: number; width: number; height: number };
  source_center: { x: number; y: number };
  target_frame: number;
  video_natural_width: number;
  video_natural_height: number;
};

export type NormalRecord = {
  record_id: string;
  created_at?: string;
  video_path?: string;
  balance_voltage_V?: number;
  target?: Partial<NormalTarget>;
  boundary?: Partial<NormalBoundarySuggestion>;
  grid?: NormalGrid;
  tracking_stats?: Record<string, number>;
  crossing_events?: Array<Record<string, unknown>>;
  fit?: Record<string, unknown>;
  q?: Record<string, unknown>;
  status: "valid" | "diagnostic";
  selected?: boolean;
  qa_fixture?: boolean;
  recovery_suggestions?: string[];
};

export type NormalSession = {
  schema_version?: number;
  session_id?: string;
  created_at?: string;
  updated_at?: string;
  records: NormalRecord[];
  counts: { total: number; valid: number; selected_valid: number };
  eligible_for_inversion: boolean;
  qa_fixture?: boolean;
  inversion?: Record<string, unknown>;
  active_video?: Record<string, unknown> | null;
};

export type NormalPrepareVideoResponse = {
  metadata: VideoMetadata;
  video_url: string;
  boundary: {
    samples: Array<Record<string, unknown>>;
    operations: Array<Record<string, unknown>>;
    suggestion: NormalBoundarySuggestion;
  };
  grid: NormalGrid;
  session: NormalSession;
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

export type DesktopApi = {
  initializeApp: () => Promise<AppInitialization>;
  runtimePaths: () => Promise<Record<string, string>>;
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
  normalInitialize: (payload?: unknown) => Promise<{ session: NormalSession; config?: Record<string, unknown> }>;
  normalPrepareVideo: (payload: { video_path: string }) => Promise<NormalPrepareVideoResponse>;
  normalSaveMeasurement: (payload: unknown) => Promise<{ record: NormalRecord; session: NormalSession }>;
  normalSelectRecord: (payload: { record_id: string; selected: boolean }) => Promise<{ session: NormalSession }>;
  normalRunInversion: (payload?: unknown) => Promise<{ inversion: Record<string, unknown>; session: NormalSession }>;
  normalCreateQaFixture: (payload?: unknown) => Promise<{ session: NormalSession }>;
  normalExportSession: (payload?: unknown) => Promise<unknown>;
  exportReport: (payload: { run_dir: string; include_pdf?: boolean; mode?: "folder" | "zip" }) => Promise<unknown>;
  openPath: (targetPath: string) => Promise<unknown>;
  onAnalysisProgress: (callback: (progress: ProgressEvent) => void) => () => void;
};
