import { DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, BoxSelect, FileVideo, Play, RefreshCw, Save, Search, Square, Trash2 } from "lucide-react";
import { desktopApi } from "./lib/desktopApi";
import type { VideoMetadata } from "./types";
import "./styles/app.css";

type StepState = "idle" | "running" | "complete" | "needs_confirmation" | "failed_retryable" | "complete_with_warnings";
type ProductMode = "normal" | "experimental";
type Target = { x: number; y: number; frame: number; box: [number, number, number, number] };
type WindowSuggestion = { start_frame: number; end_frame: number; start_time_s: number; end_time_s: number; flags?: string[] };
type QRecord = Record<string, any>;

const sessionPath = "runs/normal_v2/session.json";

export default function App() {
  const api = desktopApi;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [mode, setMode] = useState<ProductMode>("normal");
  const [experimentalConfirmed, setExperimentalConfirmed] = useState(false);
  const [videoPath, setVideoPath] = useState("");
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [balanceVoltage, setBalanceVoltage] = useState("");
  const [windowSuggestion, setWindowSuggestion] = useState<WindowSuggestion | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [trackPoints, setTrackPoints] = useState<Array<Record<string, any>>>([]);
  const [events, setEvents] = useState<Array<Record<string, any>>>([]);
  const [records, setRecords] = useState<QRecord[]>([]);
  const [inversion, setInversion] = useState<Record<string, any> | null>(null);
  const [algorithm, setAlgorithm] = useState<"normal" | "experimental">("normal");
  const [status, setStatus] = useState("renderer ready");
  const [step, setStep] = useState<Record<string, StepState>>({
    video: "idle",
    voltage: "idle",
    window: "idle",
    target: "idle",
    tracking: "idle",
    records: "idle",
    inversion: "idle"
  });

  const setStepState = (name: string, value: StepState) => setStep((current) => ({ ...current, [name]: value }));
  const selectedValid = useMemo(() => records.filter((record) => record.valid && record.selected !== false), [records]);
  const canSuggest = Boolean(api && metadata && Number(balanceVoltage) > 0);
  const canTrack = Boolean(api && metadata && windowSuggestion && target && Number(balanceVoltage) > 0);
  const canInvert = selectedValid.length >= 3;

  useEffect(() => {
    let canceled = false;
    void Promise.resolve(api?.loadNormalV2Session({ session_path: sessionPath })).then((result: any) => {
      if (canceled || !result?.session) {
        return;
      }
      setRecords(result.session.records || []);
      setInversion(result.session.inversion || null);
      setStepState("records", (result.session.records || []).length ? "complete" : "idle");
      setStatus("已恢复普通模式 session");
    }).catch(() => {
      if (!canceled) {
        setStatus("renderer ready");
      }
    });
    return () => {
      canceled = true;
    };
  }, [api]);

  if (!api) {
    return (
      <main className="integration-error">
        <AlertTriangle size={34} />
        <h1>桌面集成不可用</h1>
        <p>preload 或 Python worker 未连接。生产模式不会回退到 Demo API，也不会显示演示 q/e。</p>
      </main>
    );
  }

  const inspectVideoPath = async (path: string) => {
    setVideoPath(path);
    setStepState("video", "running");
    try {
      const result = await api.inspectVideo({ video_path: path });
      setMetadata(result.metadata);
      setStatus("视频检查完成");
      setStepState("video", "complete");
      if (videoRef.current) {
        videoRef.current.src = path.startsWith("file:") ? path : `file:///${path.replaceAll("\\", "/")}`;
      }
    } catch (error) {
      setStatus(`视频检查失败：${error instanceof Error ? error.message : String(error)}`);
      setStepState("video", "failed_retryable");
    }
  };

  const openVideo = async () => {
    const path = await api.openVideoDialog();
    if (path) {
      await inspectVideoPath(path);
    }
  };

  const onDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files.item(0) as (File & { path?: string }) | null;
    if (file?.path) {
      await inspectVideoPath(file.path);
    }
  };

  const suggestWindow = async () => {
    if (!canSuggest || !metadata) {
      return;
    }
    setStepState("window", "running");
    const result = (await api.suggestNormalV2Window({ video_path: metadata.path || videoPath, balance_voltage_V: Number(balanceVoltage) })) as any;
    const next = result.window as WindowSuggestion;
    setWindowSuggestion(next);
    setStepState("window", next.flags?.length ? "complete_with_warnings" : "needs_confirmation");
    seekTo(next.start_time_s);
    setStatus("已生成时间建议并跳转到开始检查位置");
  };

  const adjustBoundary = (field: "start_time_s" | "end_time_s", delta: number) => {
    if (!windowSuggestion || !metadata) {
      return;
    }
    const current = Number(windowSuggestion[field] || 0);
    const nextTime = Math.max(0, Math.min(metadata.duration_s, current + delta));
    const frameField = field === "start_time_s" ? "start_frame" : "end_frame";
    const next = { ...windowSuggestion, [field]: nextTime, [frameField]: Math.round(nextTime * metadata.fps) };
    setWindowSuggestion(next);
    seekTo(nextTime);
  };

  const seekTo = (time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = Number(time.toFixed(3));
    }
  };

  const selectTarget = () => {
    if (!metadata || !videoRef.current) {
      return;
    }
    const frame = Math.round(videoRef.current.currentTime * metadata.fps);
    setTarget({ x: metadata.width * 0.35, y: metadata.height * 0.34, frame, box: [Math.round(metadata.width * 0.35 - 8), Math.round(metadata.height * 0.34 - 8), 16, 16] });
    setStepState("target", "needs_confirmation");
    setStatus("已在当前真实帧记录目标框，可重新框选");
  };

  const runTracking = async () => {
    if (!canTrack || !metadata || !target || !windowSuggestion) {
      return;
    }
    setStepState("tracking", "running");
    const response = (await api.runNormalV2SingleDrop({
      video_path: metadata.path || videoPath,
      balance_voltage_V: Number(balanceVoltage),
      target,
      confirmed_window: {
        start_frame: windowSuggestion.start_frame,
        end_frame: windowSuggestion.end_frame
      }
    })) as any;
    setTrackPoints(response.track_points || []);
    setEvents(response.events || []);
    const qRecord = { ...response.q_record, selected: response.q_record?.selected !== false };
    const nextRecords = [...records, qRecord];
    setRecords(nextRecords);
    await api.saveNormalV2Session({ session_path: sessionPath, records: nextRecords, inversion });
    setStepState("tracking", qRecord.valid ? "complete" : "complete_with_warnings");
    setStepState("records", "complete");
    setStatus("追踪完成，q 记录已保存到 session");
  };

  const runInversion = async () => {
    if (!canInvert) {
      return;
    }
    setStepState("inversion", "running");
    const result = (await api.estimateNormalV2Elementary({ records })) as Record<string, any>;
    setInversion(result);
    await api.saveNormalV2Session({ session_path: sessionPath, records, inversion: result });
    setAlgorithm("normal");
    setStepState("inversion", "complete");
    setStatus("双算法完成并写入 session");
  };

  const exportBundle = async () => {
    if (!records.length) {
      return;
    }
    const destination = `runs/normal_v2/export_${new Date().toISOString().replace(/[:.]/g, "-")}`;
    const result = (await api.exportNormalV2Bundle({
      destination_dir: destination,
      session: { schema_version: 1, records },
      inversion
    })) as any;
    setStatus(`导出完成：${result.destination_dir ?? destination}`);
  };

  const deleteRecord = (id: string) => {
    const next = records.filter((record) => record.record_id !== id);
    setRecords(next);
    void api.saveNormalV2Session({ session_path: sessionPath, records: next, inversion });
  };

  const reviewEvent = (event: Record<string, any>) => {
    const frame = Number(event.missing_start_frame ?? 0);
    const fps = metadata?.fps || 30;
    seekTo(Math.max(0, frame / fps - 0.4));
    setStatus(`跨网格复核：${event.missing_start_frame} -> ${event.reacquired_frame}，局部循环已启用`);
  };

  if (mode === "experimental" && !experimentalConfirmed) {
    return (
      <main className="integration-error">
        <AlertTriangle size={34} />
        <h1>Experimental 风险确认</h1>
        <p>Experimental 使用现有多滴 pipeline。它的 run、输入和结果不会与普通模式 session 混用。</p>
        <button className="primary-button" onClick={() => setExperimentalConfirmed(true)}>确认进入 Experimental</button>
        <button className="ghost-button" onClick={() => setMode("normal")}>返回普通模式</button>
      </main>
    );
  }

  return (
    <div className="normal-shell">
      <header className="normal-header">
        <div>
          <h1>Millikan AI</h1>
          <p>真实初始化：renderer ready · preload API ready · worker ready · config readable</p>
        </div>
        <div className="mode-switch">
          <button className={mode === "normal" ? "selected" : ""} onClick={() => setMode("normal")}>普通模式</button>
          <button className={mode === "experimental" ? "selected" : ""} onClick={() => setMode("experimental")}>Experimental</button>
        </div>
      </header>

      <main className="normal-grid">
        <section className="video-panel" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
          <div className="panel-title">
            <span>视频播放器</span>
            <small>{step.video}</small>
          </div>
          <video ref={videoRef} data-testid="normal-video-player" className="normal-video" controls />
          <div className="toolbar">
            <button className="primary-button" onClick={openVideo}><FileVideo size={16} />打开视频</button>
            <button className="ghost-button" onClick={() => videoRef.current?.play()}><Play size={16} />播放</button>
            <button className="ghost-button" onClick={() => videoRef.current?.pause()}><Square size={16} />暂停</button>
            <input value={videoPath} onChange={(event) => setVideoPath(event.target.value)} placeholder="拖入或选择视频" />
          </div>
          <div className="metric-strip">
            <span>{metadata ? `${metadata.width} × ${metadata.height}` : "-"}</span>
            <span>{metadata ? `${metadata.fps} fps` : "-"}</span>
            <span>{metadata ? `${metadata.duration_s.toFixed(2)} s` : "-"}</span>
          </div>
        </section>

        <section className="workflow-panel">
          <div className="panel-title">
            <span>普通模式</span>
            <small>{status}</small>
          </div>
          <label className="field-row">
            <span>平衡电压</span>
            <input aria-label="平衡电压" value={balanceVoltage} onChange={(event) => setBalanceVoltage(event.target.value)} type="number" placeholder="V" />
          </label>
          <button className="primary-button" disabled={!canSuggest} title={canSuggest ? "" : "先打开视频并输入平衡电压"} onClick={suggestWindow}><Search size={16} />生成时间建议</button>
          <BoundaryEditor title="开始时间" disabled={!windowSuggestion} time={windowSuggestion?.start_time_s} onAdjust={(delta) => adjustBoundary("start_time_s", delta)} />
          <BoundaryEditor title="结束时间" disabled={!windowSuggestion} time={windowSuggestion?.end_time_s} onAdjust={(delta) => adjustBoundary("end_time_s", delta)} />
          <button className="ghost-button" disabled={!windowSuggestion} onClick={selectTarget}><BoxSelect size={16} />框选当前油滴</button>
          <div className="target-readout">{target ? `target_frame: ${target.frame}` : "target_frame: -"}</div>
          <button className="primary-button" disabled={!canTrack} onClick={runTracking}><RefreshCw size={16} />运行追踪</button>
          <div className="status-pills">
            {["video", "window", "target", "tracking", "records", "inversion"].map((name) => <span key={name}>{name}: {step[name]}</span>)}
          </div>
        </section>

        <section className="review-panel">
          <div className="panel-title">
            <span>轨迹复核</span>
            <small>{events.length ? "可复核跨网格事件" : "等待追踪"}</small>
          </div>
          <div className="legend"><span className="dot tracking" />tracking <span className="dot missing" />missing <span className="dot reacquired" />reacquired</div>
          <div className="track-list">
            {trackPoints.slice(0, 18).map((point) => <span key={point.frame_idx} className={`track-row ${point.status}`}>{point.frame_idx}: {point.status}</span>)}
          </div>
          {events.map((event, index) => (
            <button key={index} className="ghost-button" onClick={() => reviewEvent(event)}>复核 crossing {event.missing_start_frame} {"->"} {event.reacquired_frame}</button>
          ))}
        </section>

        <section className="records-panel">
          <div className="panel-title">
            <span>q 记录 session</span>
            <small>总数 {records.length} · 有效 {records.filter((record) => record.valid).length} · 选中 {selectedValid.length}</small>
          </div>
          {records.length === 0 ? <p className="empty">-</p> : records.map((record) => (
            <div className="record-row" key={record.record_id}>
              <input type="checkbox" checked={record.selected !== false} onChange={(event) => {
                const next = records.map((item) => item.record_id === record.record_id ? { ...item, selected: event.target.checked } : item);
                setRecords(next);
                void api.saveNormalV2Session({ session_path: sessionPath, records: next, inversion });
              }} />
              <strong>{record.record_id}</strong>
              <span>{record.valid ? formatSci(record.q_C) : "-"}</span>
              <button className="icon-button" aria-label={`删除 ${record.record_id}`} onClick={() => deleteRecord(record.record_id)}><Trash2 size={14} /></button>
            </div>
          ))}
          <button className="primary-button" disabled={!canInvert} title={canInvert ? "" : "至少需要 3 条已选有效 q"} onClick={runInversion}><Save size={16} />运行双算法</button>
          <button className="ghost-button" disabled={!records.length} title={records.length ? "" : "先保存至少一条 q 记录"} onClick={exportBundle}><Save size={16} />导出 session 包</button>
        </section>

        <section className="inversion-panel">
          <div className="panel-title"><span>双算法结果</span><small>{step.inversion}</small></div>
          <div className="algorithm-tabs">
            <button className={algorithm === "normal" ? "selected" : ""} onClick={() => setAlgorithm("normal")}>普通算法</button>
            <button className={algorithm === "experimental" ? "selected" : ""} onClick={() => setAlgorithm("experimental")}>Experimental 算法</button>
          </div>
          {algorithm === "normal" ? (
            <div>Normal e: {inversion?.normal_algorithm?.e_hat_C ? formatSci(inversion.normal_algorithm.e_hat_C) : "-"}</div>
          ) : (
            <div>{inversion?.experimental_algorithm?.status ?? "-"}</div>
          )}
          <div className="formula">q_i = n_i e · v_g = dy / dt · qU / d = mg</div>
        </section>
      </main>
    </div>
  );
}

function BoundaryEditor({ title, disabled, time, onAdjust }: { title: string; disabled: boolean; time?: number; onAdjust: (delta: number) => void }) {
  return (
    <div className="boundary-row">
      <strong>{title}</strong>
      <span>{time === undefined ? "-" : `${time.toFixed(2)} s`}</span>
      {[-1, -0.1, 0.1, 1].map((delta) => <button key={delta} disabled={disabled} onClick={() => onAdjust(delta)}>{delta > 0 ? "+" : ""}{delta}s</button>)}
    </div>
  );
}

function formatSci(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toExponential(3) : "-";
}
