import { ArrowLeft, FolderOpen, Play, RotateCcw, Save } from "lucide-react";

type TopBarProps = {
  view: "setup" | "analysis" | "results";
  onViewChange: (view: "setup" | "analysis" | "results") => void;
  onLoadRun: () => void;
  onExport: () => void;
  hasRun: boolean;
  onBack: () => void;
};

export function TopBar({ view, onViewChange, onLoadRun, onExport, hasRun, onBack }: TopBarProps) {
  return (
    <header className="topbar">
      <button className="icon-button" onClick={onBack} aria-label="返回模式选择" title="返回模式选择">
        <ArrowLeft size={18} />
      </button>
      <div className="window-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="topbar__brand">
        <strong>Millikan AI</strong>
        <span>Elementary charge inversion workspace</span>
      </div>
      <nav className="segmented" aria-label="主要视图">
        <button className={view === "setup" ? "active" : ""} onClick={() => onViewChange("setup")}>
          <RotateCcw size={16} />
          平台设置
        </button>
        <button className={view === "analysis" ? "active" : ""} onClick={() => onViewChange("analysis")}>
          <Play size={16} />
          运行状态
        </button>
        <button className={view === "results" ? "active" : ""} onClick={() => onViewChange("results")}>
          <Save size={16} />
          元电荷诊断
        </button>
      </nav>
      <div className="topbar__actions">
        <button className="ghost-button" onClick={onLoadRun}>
          <FolderOpen size={16} />
          打开 run
        </button>
        <button className="primary-button small" disabled={!hasRun} onClick={onExport}>
          <Save size={16} />
          导出报告
        </button>
      </div>
    </header>
  );
}
