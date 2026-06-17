import { useEffect, useMemo, useState } from "react";
import type { DragEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ManualPlatform, ProgressEvent, RunArtifacts, VideoMetadata } from "./types";
import type { NormalElementaryEstimate, NormalQRecord, NormalTarget, NormalWindow } from "./types";
import { desktopApi } from "./lib/desktopApi";
import { SplashScreen } from "./components/SplashScreen";
import { TopBar } from "./components/TopBar";
import { SetupView } from "./components/SetupView";
import { NormalSetupView } from "./components/NormalSetupView";
import { AnalysisWorkspace } from "./components/AnalysisWorkspace";
import { ResultsView } from "./components/ResultsView";
import "./styles/app.css";

type View = "setup" | "analysis" | "results";
type ProductMode = "normal" | "experimental";

const initialPlatforms: ManualPlatform[] = [
  { platform_id: "P001", start_frame: 0, end_frame: 156, voltage_V: 0, source: "manual_ui" },
  { platform_id: "P002", start_frame: 166, end_frame: 344, voltage_V: 239, source: "manual_ui" },
  { platform_id: "P003", start_frame: 355, end_frame: 542, voltage_V: 362, source: "manual_ui" }
];

export default function App() {
  const [entered, setEntered] = useState(false);
  const [view, setView] = useState<View>("setup");
  const [productMode, setProductMode] = useState<ProductMode>("normal");
  const [videoPath, setVideoPath] = useState("");
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [balanceVoltage, setBalanceVoltage] = useState(240);
  const [normalTarget, setNormalTarget] = useState<NormalTarget | null>(null);
  const [normalWindow, setNormalWindow] = useState<NormalWindow | null>(null);
  const [qRecords, setQRecords] = useState<NormalQRecord[]>([]);
  const [normalElementary, setNormalElementary] = useState<NormalElementaryEstimate | null>(null);
  const [platformCount, setPlatformCount] = useState(3);
  const [platforms, setPlatforms] = useState<ManualPlatform[]>(initialPlatforms);
  const [suggestions, setSuggestions] = useState<Array<Record<string, unknown>>>([]);
  const [artifacts, setArtifacts] = useState<RunArtifacts | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState("准备就绪");

  useEffect(() => desktopApi.onAnalysisProgress((event) => setProgress(event)), []);

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
      setNormalTarget(null);
      setNormalWindow({
        fall_start_frame: 0,
        fall_end_frame: Math.max(0, (result.metadata.frame_count || 1) - 1)
      });
      setMessage("视频检查完成。");
    } catch (error) {
      setMessage(`视频检查失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const suggestNormalWindow = async () => {
    if (!videoPath) {
      setMessage("请先选择实验视频。");
      return;
    }
    try {
      const result = (await desktopApi.suggestNormalWindow({ video_path: videoPath })) as {
        suggested_window?: { fall_start_frame?: number; fall_end_frame?: number; flags?: string[] };
      };
      const suggested = result.suggested_window;
      if (suggested?.fall_start_frame != null) {
        setNormalWindow({
          fall_start_frame: Number(suggested.fall_start_frame),
          fall_end_frame: Number(suggested.fall_end_frame ?? metadata?.frame_count ?? 1) - 1
        });
        setMessage(suggested.flags?.length ? `已生成普通模式边界建议：${suggested.flags.join(", ")}` : "已生成普通模式边界建议。");
      }
    } catch (error) {
      setMessage(`普通模式边界建议失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const runNormalAnalysis = async () => {
    if (!videoPath || !normalTarget || !normalWindow) {
      setMessage("请先选择视频、标注油滴并确认下落窗口。");
      return;
    }
    setIsRunning(true);
    setProgress({ percent: 0.2, label: "normal tracking" });
    setView("analysis");
    try {
      const response = await desktopApi.runNormalSingleDrop({
        video_path: videoPath,
        balance_voltage_V: balanceVoltage,
        target: normalTarget,
        confirmed_window: normalWindow
      });
      const normal = response.normal_result ?? response.artifacts?.normal_result;
      const qRecord = normal?.q_record;
      if (qRecord?.record_id) {
        setQRecords((current) => {
          const existing = new Set(current.map((record) => record.record_id));
          const nextRecord = { ...qRecord, selected: qRecord.selected !== false };
          return existing.has(nextRecord.record_id) ? current : [...current, nextRecord];
        });
      }
      setArtifacts({
        ...(response.artifacts ?? {}),
        run_dir: response.run_dir ?? response.artifacts?.run_dir,
        manifest: response.manifest ?? response.artifacts?.manifest,
        normal_result: normal
      });
      setProgress({ percent: 1, label: "normal q record" });
      setView("results");
      const usableNow = qRecord?.usable_for_inversion ? qRecords.filter((record) => record.selected !== false && record.usable_for_inversion).length + 1 : qRecords.filter((record) => record.selected !== false && record.usable_for_inversion).length;
      setMessage(`普通模式完成。当前可用于盲反演的 q：${usableNow}`);
    } catch (error) {
      setMessage(`普通模式分析失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsRunning(false);
    }
  };

  const toggleQRecord = (recordId: string) => {
    setQRecords((current) => current.map((record) => (record.record_id === recordId ? { ...record, selected: record.selected === false } : record)));
  };

  const estimateNormalElementary = async () => {
    const usable = qRecords.filter((record) => record.selected !== false && record.usable_for_inversion).length;
    if (usable < 3) {
      setMessage(`可用于盲反演的 q 只有 ${usable} 条，至少需要 3 条。`);
      return;
    }
    try {
      const result = await desktopApi.estimateNormalElementary({ q_records: qRecords });
      setNormalElementary(result);
      setMessage(`双盲反演完成。可用 q：${result.usable_q_count}`);
    } catch (error) {
      setMessage(`双盲反演失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const openVideo = async () => {
    const path = await desktopApi.openVideoDialog();
    if (path) {
      await inspectVideo(path);
    }
  };

  const acceptVideoFile = async (path: string) => {
    if (!path) {
      return;
    }
    await inspectVideo(path);
  };

  useEffect(() => {
    const handleNativeDrop = (event: MessageEvent) => {
      const path = typeof event.data?.path === "string" && event.data.type === "millikan-video-drop" ? event.data.path : "";
      if (path) {
        void acceptVideoFile(path);
      }
    };
    window.addEventListener("message", handleNativeDrop);
    return () => window.removeEventListener("message", handleNativeDrop);
  }, []);

  const handleVideoDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const path = extractDroppedVideoPath(event);
    if (!path) {
      setMessage("拖入失败：请直接拖入一个本地视频文件。");
      return;
    }
    void acceptVideoFile(path);
  };

  const openRun = async () => {
    const runDir = await desktopApi.openRunDialog();
    if (!runDir) {
      return;
    }
    try {
      const result = await desktopApi.loadRun({ run_dir: runDir });
      setArtifacts(result.artifacts);
      if (result.artifacts.normal_result?.q_record) {
        setQRecords([result.artifacts.normal_result.q_record]);
      }
      setProgress({ percent: 1, label: "loaded run" });
      setView("results");
      setMessage("已加载运行结果。");
    } catch (error) {
      setMessage(`加载 run 失败：${error instanceof Error ? error.message : String(error)}`);
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
    } catch (error) {
      setMessage(`自动边界检测失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const runAnalysis = async () => {
    const path = videoPath || metadata?.path;
    if (!path) {
      setMessage("请先选择实验视频。");
      return;
    }
    setIsRunning(true);
    setProgress({ percent: 0, label: "queued" });
    setView("analysis");
    try {
      const response = await desktopApi.runAnalysis({
        video_path: path,
        manual_platforms: normalizedPlatforms
      });
      setArtifacts(response.artifacts ?? { manifest: response.manifest, run_dir: response.run_dir });
      setProgress({ percent: 1, label: "write manifest" });
      setView("results");
      setMessage(response.validation_errors?.length ? `分析完成，但有 ${response.validation_errors.length} 个校验问题。` : "分析完成。");
    } catch (error) {
      setMessage(`分析失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsRunning(false);
    }
  };

  const exportReport = async () => {
    if (!artifacts?.run_dir) {
      setMessage("没有可导出的运行结果。");
      return;
    }
    try {
      const usable = qRecords.filter((record) => record.selected !== false && record.usable_for_inversion).length;
      if (productMode === "normal") {
        setMessage(`导出前检查：当前可用于盲反演的 q 为 ${usable} 条。`);
      }
      const result = await desktopApi.exportReport({ run_dir: artifacts.run_dir, include_pdf: true, mode: "folder" });
      setMessage(JSON.stringify(result).includes("canceled") ? "已取消导出。" : "报告和数据包已导出。");
    } catch (error) {
      setMessage(`导出失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const openRunFolder = async () => {
    if (artifacts?.run_dir) {
      await desktopApi.openPath(artifacts.run_dir);
    }
  };

  return (
    <div className="app-shell">
      <AnimatePresence mode="wait">
        {!entered ? (
          <motion.div key="splash" initial={{ opacity: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.42 }}>
            <SplashScreen selectedMode={productMode} onModeChange={setProductMode} onEnter={() => setEntered(true)} />
          </motion.div>
        ) : (
          <motion.div
            key="app"
            className="desktop-frame"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.48 }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleVideoDrop}
          >
            <TopBar view={view} onViewChange={setView} onLoadRun={openRun} onExport={exportReport} hasRun={Boolean(artifacts?.run_dir)} />
            <AnimatePresence mode="wait">
              {view === "setup" && (
                <motion.div key="setup" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
                  {productMode === "normal" ? (
                    <NormalSetupView
                      videoPath={videoPath}
                      metadata={metadata}
                      balanceVoltage={balanceVoltage}
                      target={normalTarget}
                      window={normalWindow}
                      qRecords={qRecords}
                      elementary={normalElementary}
                      isRunning={isRunning}
                      onOpenVideo={openVideo}
                      onVideoPath={setVideoPath}
                      onInspect={inspectVideo}
                      onVideoDrop={acceptVideoFile}
                      onBalanceVoltage={setBalanceVoltage}
                      onTarget={setNormalTarget}
                      onSuggestWindow={suggestNormalWindow}
                      onWindow={setNormalWindow}
                      onRun={runNormalAnalysis}
                      onToggleRecord={toggleQRecord}
                      onEstimate={estimateNormalElementary}
                      onUseExperimental={() => setProductMode("experimental")}
                    />
                  ) : (
                    <SetupView
                      videoPath={videoPath}
                      metadata={metadata}
                      platformCount={platformCount}
                      platforms={platforms}
                      suggestions={suggestions}
                      onOpenVideo={openVideo}
                      onVideoPath={setVideoPath}
                      onInspect={inspectVideo}
                      onVideoDrop={acceptVideoFile}
                      onPlatformCount={updatePlatformCount}
                      onPlatformChange={(index, platform) => setPlatforms((current) => current.map((item, itemIndex) => (itemIndex === index ? platform : item)))}
                      onAddPlatform={() => updatePlatformCount(platformCount + 1)}
                      onRemovePlatform={(index) => {
                        setPlatforms((current) => current.filter((_item, itemIndex) => itemIndex !== index));
                        setPlatformCount((current) => Math.max(1, current - 1));
                      }}
                      onDetectBoundaries={detectBoundaries}
                      onRun={runAnalysis}
                      onUseNormal={() => setProductMode("normal")}
                    />
                  )}
                </motion.div>
              )}
              {view === "analysis" && (
                <motion.div key="analysis" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
                  <AnalysisWorkspace artifacts={artifacts} progress={progress} isRunning={isRunning} onRun={runAnalysis} onShowResults={() => setView("results")} />
                </motion.div>
              )}
              {view === "results" && (
                <motion.div key="results" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
                  <ResultsView artifacts={artifacts} normalRecords={qRecords} normalElementary={normalElementary} onExport={exportReport} onOpenRun={openRunFolder} />
                </motion.div>
              )}
            </AnimatePresence>
            <div className="status-toast" role="status">
              {message}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function extractDroppedVideoPath(event: DragEvent<HTMLElement>) {
  const file = event.dataTransfer.files.item(0) as (File & { path?: string }) | null;
  const directPath = file?.path || event.dataTransfer.getData("text/plain");
  if (!directPath) {
    return "";
  }
  return decodeURI(directPath.replace(/^file:\/\/\//i, "")).replace(/\//g, "\\");
}
