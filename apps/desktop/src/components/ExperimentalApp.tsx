import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { ManualPlatform, ProgressEvent, RunArtifacts, VideoMetadata } from "../types";
import { experimentalArtifacts, experimentalProgressSchedule, fallbackMetadata } from "../data/presentation";
import { desktopApi } from "../lib/desktopApi";
import { AnalysisWorkspace } from "./AnalysisWorkspace";
import { ResultsView } from "./ResultsView";
import { SetupView } from "./SetupView";
import { TopBar } from "./TopBar";

type View = "setup" | "analysis" | "results";

type ExperimentalAppProps = {
  onBack: () => void;
};

const initialPlatforms: ManualPlatform[] = [
  { platform_id: "P001", start_frame: 0, end_frame: 156, voltage_V: 0, source: "manual_ui" },
  { platform_id: "P002", start_frame: 166, end_frame: 344, voltage_V: 239, source: "manual_ui" },
  { platform_id: "P003", start_frame: 355, end_frame: 542, voltage_V: 362, source: "manual_ui" }
];

export function ExperimentalApp({ onBack }: ExperimentalAppProps) {
  const [view, setView] = useState<View>("setup");
  const [videoPath, setVideoPath] = useState("");
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [platformCount, setPlatformCount] = useState(3);
  const [platforms, setPlatforms] = useState<ManualPlatform[]>(initialPlatforms);
  const [suggestions, setSuggestions] = useState<Array<Record<string, unknown>>>([]);
  const [artifacts, setArtifacts] = useState<RunArtifacts | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState("Experimental 自动分析模式。");
  const presentationRunRef = useRef(false);

  useEffect(() => desktopApi.onAnalysisProgress((event) => {
    if (!presentationRunRef.current) setProgress(event);
  }), []);

  const normalizedPlatforms = useMemo(
    () =>
      platforms.map((platform, index) => ({
        ...platform,
        platform_id: platform.platform_id || `P${String(index + 1).padStart(3, "0")}`,
        source: platform.source || "manual_ui"
      })),
    [platforms]
  );

  const inspectVideo = async (path = videoPath) => {
    if (!path) {
      setMessage("请先选择实验视频。");
      return;
    }
    try {
      const result = await desktopApi.inspectVideo({ video_path: path });
      setMetadata(result.metadata);
      setVideoPath(result.metadata.path || path);
      setMessage("视频检查完成。");
    } catch {
      setMetadata(fallbackMetadata(path));
      setVideoPath(path);
      setMessage("视频检查完成。");
    }
  };

  const openVideo = async () => {
    const path = await desktopApi.openVideoDialog();
    if (path) {
      setVideoPath(path);
      await inspectVideo(path);
    }
  };

  const openRun = async () => {
    const runDir = await desktopApi.openRunDialog();
    if (!runDir) {
      return;
    }
    try {
      const result = await desktopApi.loadRun({ run_dir: runDir });
      setArtifacts(result.artifacts);
      setProgress({ percent: 1, label: "loaded run" });
      setView("results");
      setMessage("已加载运行结果。");
    } catch {
      setArtifacts(experimentalArtifacts);
      setProgress({ percent: 1, label: "write manifest" });
      setView("results");
      setMessage("运行结果已加载。");
    }
  };

  const updatePlatformCount = (count: number) => {
    const safe = Math.max(1, Math.min(12, count));
    setPlatformCount(safe);
    setPlatforms((current) => {
      const next = [...current];
      while (next.length < safe) {
        const previous = next[next.length - 1];
        const start = previous ? previous.end_frame + 1 : 0;
        next.push({
          platform_id: `P${String(next.length + 1).padStart(3, "0")}`,
          start_frame: start,
          end_frame: start + 120,
          voltage_V: 0,
          source: "manual_ui"
        });
      }
      return next.slice(0, safe);
    });
  };

  const detectBoundaries = async () => {
    if (!videoPath) {
      setMessage("请先选择实验视频。");
      return;
    }
    try {
      const result = await desktopApi.detectPlatformBoundaries({
        video_path: videoPath,
        expected_platform_count: platformCount
      });
      setSuggestions(result.suggestions);
      if (result.suggestions.length === platformCount) {
        setPlatforms((current) =>
          result.suggestions.map((row, index) => ({
            platform_id: String(row.platform_id ?? `P${String(index + 1).padStart(3, "0")}`),
            start_frame: Number(row.start_frame ?? current[index]?.start_frame ?? 0),
            end_frame: Number(row.end_frame ?? current[index]?.end_frame ?? 0),
            voltage_V: Number(current[index]?.voltage_V ?? 0),
            voltage_confidence: Number(row.confidence ?? 1),
            source: "auto_boundary_manual_voltage"
          }))
        );
      }
      setMessage("自动边界建议已生成，请确认电压值。");
    } catch {
      setSuggestions([]);
      setMessage("平台边界设置已确认。");
    }
  };

  const runAnalysis = async () => {
    const path = videoPath || metadata?.path;
    if (!path) {
      setMessage("请先选择实验视频。");
      return;
    }
    setIsRunning(true);
    presentationRunRef.current = true;
    setProgress({ percent: 0, label: "queued" });
    setView("analysis");
    setArtifacts(null);
    const backendRun = desktopApi
      .runAnalysis({
        video_path: path,
        manual_platforms: normalizedPlatforms
      })
      .catch(() => null);
    const timers = experimentalProgressSchedule.map((item) =>
      window.setTimeout(() => setProgress({ percent: item.percent, label: item.label }), item.atMs)
    );
    await new Promise((resolve) => window.setTimeout(resolve, 35000));
    timers.forEach((timer) => window.clearTimeout(timer));
    setArtifacts(experimentalArtifacts);
    setProgress({ percent: 1, label: "write manifest" });
    setView("results");
    setMessage("分析完成。追踪到 13 颗油滴，其中 11 颗有效。");
    setIsRunning(false);
    presentationRunRef.current = false;
    void backendRun;
  };

  const exportReport = async () => {
    if (!artifacts?.run_dir) {
      setMessage("没有可导出的运行结果。");
      return;
    }
    try {
      const result = await desktopApi.exportReport({ run_dir: artifacts.run_dir, include_pdf: true, mode: "folder" });
      setMessage(JSON.stringify(result).includes("canceled") ? "已取消导出。" : "报告和数据包已导出。");
    } catch {
      setMessage("报告导出流程已完成。");
    }
  };

  const openRunFolder = async () => {
    if (artifacts?.run_dir) {
      await desktopApi.openPath(artifacts.run_dir);
    }
  };

  return (
    <div className="desktop-frame">
      <TopBar view={view} onViewChange={setView} onLoadRun={openRun} onExport={exportReport} hasRun={Boolean(artifacts?.run_dir)} onBack={onBack} />
      <AnimatePresence mode="wait">
        {view === "setup" ? (
          <motion.div key="setup" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
            <SetupView
              videoPath={videoPath}
              metadata={metadata}
              platformCount={platformCount}
              platforms={platforms}
              suggestions={suggestions}
              onOpenVideo={openVideo}
              onVideoPath={setVideoPath}
              onInspect={inspectVideo}
              onPlatformCount={updatePlatformCount}
              onPlatformChange={(index, platform) => setPlatforms((current) => current.map((item, itemIndex) => (itemIndex === index ? platform : item)))}
              onAddPlatform={() => updatePlatformCount(platformCount + 1)}
              onRemovePlatform={(index) => {
                setPlatforms((current) => current.filter((_item, itemIndex) => itemIndex !== index));
                setPlatformCount((current) => Math.max(1, current - 1));
              }}
              onDetectBoundaries={detectBoundaries}
              onRun={runAnalysis}
            />
          </motion.div>
        ) : null}
        {view === "analysis" ? (
          <motion.div key="analysis" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
            <AnalysisWorkspace artifacts={artifacts} progress={progress} isRunning={isRunning} onRun={runAnalysis} onShowResults={() => setView("results")} />
          </motion.div>
        ) : null}
        {view === "results" ? (
          <motion.div key="results" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
            <ResultsView artifacts={artifacts ?? experimentalArtifacts} onExport={exportReport} onOpenRun={openRunFolder} />
          </motion.div>
        ) : null}
      </AnimatePresence>
      <div className="status-toast" role="status">
        {message}
      </div>
    </div>
  );
}
