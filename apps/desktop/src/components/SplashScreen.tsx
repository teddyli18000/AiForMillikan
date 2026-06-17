import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ChevronRight, FlaskConical, Gauge } from "lucide-react";

type SplashScreenProps = {
  selectedMode: "normal" | "experimental";
  onModeChange: (mode: "normal" | "experimental") => void;
  onEnter: () => void;
};

export function SplashScreen({ selectedMode, onModeChange, onEnter }: SplashScreenProps) {
  const [loadPercent, setLoadPercent] = useState(0);
  const particles = Array.from({ length: 18 }, (_, index) => index);
  const ready = loadPercent >= 100;

  useEffect(() => {
    const started = window.setInterval(() => {
      setLoadPercent((current) => Math.min(100, current + (current < 72 ? 7 : 4)));
    }, 90);
    return () => window.clearInterval(started);
  }, []);

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
        <div className="splash-loader" aria-label="应用加载进度">
          <div>
            <span>{ready ? "加载完成" : "正在加载分析工作台"}</span>
            <strong>{loadPercent}%</strong>
          </div>
          <i style={{ width: `${loadPercent}%` }} />
        </div>
        <motion.div className="splash-mode-card" animate={{ opacity: ready ? 1 : 0.5, y: ready ? 0 : 8 }}>
          <button className={selectedMode === "normal" ? "active" : ""} disabled={!ready} onClick={() => onModeChange("normal")}>
            <Gauge size={18} />
            <span>普通模式</span>
            <small>单滴框选，逐条累积 q</small>
          </button>
          <button className={selectedMode === "experimental" ? "active" : ""} disabled={!ready} onClick={() => onModeChange("experimental")}>
            <FlaskConical size={18} />
            <span>Experimental</span>
            <small>多滴探索，需要人工复核</small>
          </button>
        </motion.div>
        <button className="hero-action" onClick={onEnter} disabled={!ready}>
          <span>进入{selectedMode === "normal" ? "普通模式" : "Experimental"}</span>
          <ChevronRight size={20} />
        </button>
      </motion.div>
    </section>
  );
}
