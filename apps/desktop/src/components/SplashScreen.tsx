import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";

type SplashScreenProps = {
  onEnter: () => void;
};

export function SplashScreen({ onEnter }: SplashScreenProps) {
  const particles = Array.from({ length: 18 }, (_, index) => index);
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
        <button className="hero-action" onClick={onEnter}>
          <span>进入分析工作台</span>
          <ChevronRight size={20} />
        </button>
        <div className="shimmer-line" aria-hidden="true" />
      </motion.div>
    </section>
  );
}
