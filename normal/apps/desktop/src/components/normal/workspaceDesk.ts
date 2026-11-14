import type { Dispatch, RefObject, SetStateAction } from "react";
import type {
  NormalBoundary,
  NormalCrossingEvent,
  NormalGrid,
  NormalInversionResult,
  NormalProgressEvent,
  NormalRecord,
  NormalSession,
  VideoMetadata
} from "../../types";
import type { VideoBox, VideoPoint } from "./videoGeometry";
import type { MeasurementStage } from "./workspaceModel";

type Setter<T> = Dispatch<SetStateAction<T>>;

// 三个行为 hook 共用同一批工作台状态，类型在这里收拢一次。
export type WorkspaceDesk = {
  videoRef: RefObject<HTMLVideoElement | null>;
  overlayRef: RefObject<HTMLDivElement | null>;
  stage: MeasurementStage;
  setStage: Setter<MeasurementStage>;
  session: NormalSession | null;
  setSession: Setter<NormalSession | null>;
  defaultParameters: Record<string, any> | null;
  setDefaultParameters: Setter<Record<string, any> | null>;
  metadata: VideoMetadata | null;
  setMetadata: Setter<VideoMetadata | null>;
  videoPath: string;
  setVideoPath: Setter<string>;
  videoUrl: string;
  setVideoUrl: Setter<string>;
  boundary: NormalBoundary;
  setBoundary: Setter<NormalBoundary>;
  boundaryEdited: boolean;
  setBoundaryEdited: Setter<boolean>;
  grid: NormalGrid | null;
  setGrid: Setter<NormalGrid | null>;
  selectionTime: number;
  setSelectionTime: Setter<number>;
  selectionBox: VideoBox | null;
  setSelectionBox: Setter<VideoBox | null>;
  selectionAnchor: VideoPoint | null;
  setSelectionAnchor: Setter<VideoPoint | null>;
  balanceVoltage: string;
  setBalanceVoltage: Setter<string>;
  balanceConfirmed: boolean;
  setBalanceConfirmed: Setter<boolean>;
  advancedOpen: boolean;
  setAdvancedOpen: Setter<boolean>;
  overrideFields: Record<string, string>;
  setOverrideFields: Setter<Record<string, string>>;
  selectedRecordId: string | null;
  setSelectedRecordId: Setter<string | null>;
  retrySourceRecordId: string | null;
  setRetrySourceRecordId: Setter<string | null>;
  currentCrossing: NormalCrossingEvent | null;
  setCurrentCrossing: Setter<NormalCrossingEvent | null>;
  inversion: NormalInversionResult | null;
  setInversion: Setter<NormalInversionResult | null>;
  progress: NormalProgressEvent | null;
  setProgress: Setter<NormalProgressEvent | null>;
  busy: boolean;
  setBusy: Setter<boolean>;
  message: string;
  setMessage: Setter<string>;
  isPlaying: boolean;
  setIsPlaying: Setter<boolean>;
  currentTime: number;
  setCurrentTime: Setter<number>;
  duration: number;
  setDuration: Setter<number>;
  nextDropDialogOpen: boolean;
  setNextDropDialogOpen: Setter<boolean>;
  selectedRecord: NormalRecord | null;
  retrySourceRecord: NormalRecord | null;
  crossings: NormalCrossingEvent[];
  allCrossingsSameDrop: boolean;
  keptValidCount: number;
  gridLineCount: number;
  effectiveTopPx: number;
  effectiveBottomPx: number;
  selectionWindow: { start_s: number; end_s: number; source?: string };
  selectedOverlayUrl: string;
  playerStartS: number;
  playerEndS: number;
  selectedTrackFrames: NonNullable<NormalRecord["track_review_frames"]>;
  inReviewOrResults: boolean;
  showingTrackFrames: boolean;
  mainVideoUrl: string;
  showingTrackOverlay: boolean;
  canKeepRecord: boolean;
};
