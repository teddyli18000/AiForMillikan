import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { AppInitialization } from "./types";
import { desktopApi } from "./lib/desktopApi";
import { SplashScreen } from "./components/SplashScreen";
import { ExperimentalApp } from "./components/ExperimentalApp";
import { NormalWorkspace } from "./components/normal/NormalWorkspace";
import "./styles/app.css";

type Mode = "normal" | "experimental";

export default function App() {
  const [initialization, setInitialization] = useState<AppInitialization | null>(null);
  const [initError, setInitError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [experimentalConfirmed, setExperimentalConfirmed] = useState(false);

  const initialize = async () => {
    setInitError(null);
    try {
      const result = await desktopApi.initializeApp();
      setInitialization(result);
      if (!result.ok) setInitError("初始化未完成，请检查失败项后重试。");
    } catch (error) {
      setInitError(error instanceof Error ? error.message : String(error));
    }
  };

  useEffect(() => {
    void initialize();
  }, []);

  const chooseMode = (next: Mode) => {
    if (next === "experimental" && !experimentalConfirmed) {
      setMode("experimental");
      return;
    }
    setMode(next);
  };

  return (
    <div className="app-shell">
      <AnimatePresence mode="wait">
        {!mode ? (
          <motion.div key="splash" initial={{ opacity: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.42 }}>
            <SplashScreen initialization={initialization} error={initError} onRetry={initialize} onEnter={chooseMode} />
          </motion.div>
        ) : mode === "normal" ? (
          <motion.div key="normal" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
            <NormalWorkspace onSwitchMode={chooseMode} />
          </motion.div>
        ) : experimentalConfirmed ? (
          <motion.div key="experimental" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
            <ExperimentalApp />
          </motion.div>
        ) : (
          <motion.div key="experimental-confirm" className="desktop-frame" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
            <section className="experimental-confirm glass-panel">
              <h2>进入 Experimental 前请确认</h2>
              <p>Experimental 是多滴、多平台自动分析流程。油滴身份关联依赖视觉算法，结果需要人工复核。</p>
              <div className="panel-actions">
                <button className="ghost-button" onClick={() => setMode(null)}>返回模式选择</button>
                <button
                  className="primary-button"
                  onClick={() => {
                    setExperimentalConfirmed(true);
                    setMode("experimental");
                  }}
                >
                  我了解风险，进入 Experimental
                </button>
              </div>
            </section>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
