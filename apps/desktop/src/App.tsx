import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { AppMode } from "./types";
import { ExperimentalApp } from "./components/ExperimentalApp";
import { NormalWorkspace } from "./components/normal/NormalWorkspace";
import { SplashScreen } from "./components/SplashScreen";
import "./styles/app.css";

export default function App() {
  const [mode, setMode] = useState<AppMode | null>(null);

  return (
    <div className="app-shell">
      <AnimatePresence mode="wait">
        {mode === null ? (
          <motion.div key="splash" initial={{ opacity: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.42 }}>
            <SplashScreen onEnter={setMode} />
          </motion.div>
        ) : (
          <motion.div key={mode} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.48 }}>
            {mode === "normal" ? <NormalWorkspace onBack={() => setMode(null)} /> : <ExperimentalApp />}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
