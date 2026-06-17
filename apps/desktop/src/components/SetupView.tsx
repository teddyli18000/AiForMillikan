import { ChangeEvent, DragEvent } from "react";
import { FileVideo, Plus, Search, SlidersHorizontal, Trash2, UploadCloud } from "lucide-react";
import type { ManualPlatform, VideoMetadata } from "../types";
import { fmtNumber } from "../lib/format";

type SetupViewProps = {
  videoPath: string;
  metadata: VideoMetadata | null;
  platformCount: number;
  platforms: ManualPlatform[];
  suggestions: Array<Record<string, unknown>>;
  onOpenVideo: () => void;
  onVideoPath: (path: string) => void;
  onInspect: (path?: string) => void;
  onPlatformCount: (count: number) => void;
  onPlatformChange: (index: number, platform: ManualPlatform) => void;
  onAddPlatform: () => void;
  onRemovePlatform: (index: number) => void;
  onDetectBoundaries: () => void;
  onRun: () => void;
};

export function SetupView({
  videoPath,
  metadata,
  platformCount,
  platforms,
  suggestions,
  onOpenVideo,
  onVideoPath,
  onInspect,
  onPlatformCount,
  onPlatformChange,
  onAddPlatform,
  onRemovePlatform,
  onDetectBoundaries,
  onRun
}: SetupViewProps) {
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files.item(0) as (File & { path?: string }) | null;
    if (file?.path) {
      onVideoPath(file.path);
      onInspect(file.path);
    }
  };

  return (
    <main className="setup-grid">
      <section
        className="drop-zone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
        aria-label="拖入实验视频"
      >
        <div className="drop-zone__visual">
          <UploadCloud size={36} />
        </div>
        <div>
          <h2>拖入实验视频</h2>
          <p>支持 MP4 / MOV / AVI；当前主线不启用 OCR，电压值由用户确认。</p>
        </div>
        <div className="path-row">
          <input
            value={videoPath}
            onChange={(event) => onVideoPath(event.target.value)}
            placeholder="选择或拖入视频路径"
            aria-label="视频路径"
          />
          <button className="ghost-button" onClick={onOpenVideo}>
            <FileVideo size={17} />
            打开文件
          </button>
          <button className="primary-button" onClick={() => onInspect()}>
            检查视频
          </button>
        </div>
      </section>

      <section className="glass-panel metadata-panel">
        <div className="panel-heading">
          <span>视频元数据</span>
          <small>{metadata?.readable ? "OpenCV 可读" : "等待检查"}</small>
        </div>
        <div className="metric-grid">
          <Metric label="分辨率" value={metadata ? `${metadata.width} × ${metadata.height}` : "—"} />
          <Metric label="FPS" value={fmtNumber(metadata?.fps)} />
          <Metric label="帧数" value={fmtNumber(metadata?.frame_count, 0)} />
          <Metric label="时长" value={`${fmtNumber(metadata?.duration_s)} s`} />
        </div>
      </section>

      <section className="glass-panel platform-panel">
        <div className="panel-heading">
          <span>平台设置</span>
          <div className="stepper">
            <button onClick={() => onPlatformCount(Math.max(1, platformCount - 1))}>−</button>
            <strong>{platformCount}</strong>
            <button onClick={() => onPlatformCount(platformCount + 1)}>＋</button>
          </div>
        </div>
        <div className="timeline">
          {(suggestions.length ? suggestions : platforms).map((item, index) => (
            <span
              key={`${item.platform_id ?? index}`}
              style={{
                left: `${Math.min(92, 6 + index * (86 / Math.max(1, (suggestions.length || platforms.length) - 1)))}%`
              }}
              title={`${item.platform_id ?? `P${index + 1}`}`}
            />
          ))}
        </div>
        <div className="table-wrap compact">
          <table>
            <thead>
              <tr>
                <th>平台</th>
                <th>起始帧</th>
                <th>结束帧</th>
                <th>电压 V</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {platforms.map((platform, index) => (
                <tr key={index}>
                  <td>{platform.platform_id || `P${String(index + 1).padStart(3, "0")}`}</td>
                  <td>
                    <NumericCell
                      value={platform.start_frame}
                      onChange={(value) => onPlatformChange(index, { ...platform, start_frame: value })}
                    />
                  </td>
                  <td>
                    <NumericCell
                      value={platform.end_frame}
                      onChange={(value) => onPlatformChange(index, { ...platform, end_frame: value })}
                    />
                  </td>
                  <td>
                    <NumericCell
                      value={platform.voltage_V}
                      onChange={(value) => onPlatformChange(index, { ...platform, voltage_V: value })}
                    />
                  </td>
                  <td>
                    <button className="icon-button" onClick={() => onRemovePlatform(index)} aria-label="删除平台">
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-actions">
          <button className="ghost-button" onClick={onAddPlatform}>
            <Plus size={16} />
            添加平台
          </button>
          <button className="ghost-button" onClick={onDetectBoundaries}>
            <Search size={16} />
            自动边界建议
          </button>
          <button className="primary-button" onClick={onRun}>
            开始分析
          </button>
        </div>
      </section>

      <section className="glass-panel constants-panel">
        <div className="panel-heading">
          <span>物理常数</span>
          <SlidersHorizontal size={17} />
        </div>
        <div className="constant-list">
          <Constant label="测量距离 l" value="1.5 mm" />
          <Constant label="极板距离 d" value="5.0 mm" />
          <Constant label="空气温度" value="20 °C" />
          <Constant label="油滴密度" value="981 kg/m³" />
          <Constant label="方向约定" value="+Y 向下，正电压向上推" />
        </div>
      </section>
    </main>
  );
}

function NumericCell({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const number = Number(event.target.value);
    onChange(Number.isFinite(number) ? number : 0);
  };
  return <input className="cell-input" value={value} type="number" onChange={handleChange} />;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Constant({ label, value }: { label: string; value: string }) {
  return (
    <div className="constant-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
