import { motion } from "framer-motion";
import { AlertTriangle, Beaker, CheckCircle2, ChevronRight, RefreshCw } from "lucide-react";
import type { AppInitialization } from "../types";

type SplashScreenProps = {
  initialization: AppInitialization | null;
  error: string | null;
  onRetry: () => void;
  onEnter: (mode: "normal" | "experimental") => void;
};

export function SplashScreen({ initialization, error, onRetry, onEnter }: SplashScreenProps) {
  const particles = Array.from({ length: 18 }, (_, index) => index);
  const ready = initialization?.ok === true;
  return (
    <section className="splash" aria-label="Millikan AI opening">
      <div className="splash__field" aria-hidden="true">
        {Array.from({ length: 8 }, (_, index) => (
          <span key={index} className="field-line" style={{ left: `${12 + index * 11}%` }} />
        ))}
        {particles.map((particle) => (
          <motion.span
            key={particle}
            className="oil-particle"
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 680, opacity: [0, 0.95, 0] }}
            transition={{
              duration: 5.5 + (particle % 5) * 0.42,
              repeat: Infinity,
              delay: particle * 0.18,
              ease: "easeInOut"
            }}
            style={{
              left: `${10 + ((particle * 19) % 78)}%`,
              width: `${6 + (particle % 4)}px`,
              height: `${6 + (particle % 4)}px`
            }}
          />
        ))}
        <span className="splash__oil splash__oil--large" />
        <span className="splash__oil splash__oil--mid" />
        <span className="splash__oil splash__oil--small" />
        <div className="splash__electric">
          <span>+</span>
          <strong>E</strong>
          <span>−</span>
        </div>
      </div>
      <motion.div
        className="splash__content"
        initial={{ opacity: 0, y: 28, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.72, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <h1>Millikan AI</h1>
        <p>从实验视频盲反演元电荷</p>
        <div className="startup-checks" aria-label="初始化检查">
          {(initialization?.checks ?? [
            { id: "renderer_ready", label: "renderer ready", ok: true },
            { id: "preload_api_ready", label: "preload API ready", ok: false },
            { id: "packaged_worker_health", label: "packaged worker health", ok: false },
            { id: "config_readable", label: "配置资源可读", ok: false },
            { id: "normal_session_readable", label: "普通模式 session 可读", ok: false },
          ]).map((check) => (
            <div key={check.id} className={check.ok ? "startup-check ok" : "startup-check pending"}>
              {check.ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
              <span>{check.label}</span>
            </div>
          ))}
        </div>
        {error && (
          <div className="startup-error">
            <span>{error}</span>
            <button className="ghost-button" onClick={onRetry}><RefreshCw size={15} /> 重试</button>
          </div>
        )}
        <div className="mode-cards">
          <button className="mode-card primary" disabled={!ready} onClick={() => onEnter("normal")}>
            <CheckCircle2 size={22} />
            <strong>普通模式</strong>
            <span>平衡电压到 0V 下落，逐颗油滴测量 q。</span>
            <ChevronRight size={18} />
          </button>
          <button className="mode-card" disabled={!ready} onClick={() => onEnter("experimental")}>
            <Beaker size={22} />
            <strong>Experimental</strong>
            <span>多滴、多平台自动分析；身份关联需人工复核。</span>
            <ChevronRight size={18} />
          </button>
        </div>
        <div className="shimmer-line" aria-hidden="true" />
      </motion.div>
    </section>
  );
}
