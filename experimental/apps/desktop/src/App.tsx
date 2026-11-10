import { motion } from "framer-motion";
import { ExperimentalApp } from "./components/ExperimentalApp";
import "./styles/app.css";

export default function App() {
  return (
    <div className="app-shell">
      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.48 }}>
        <ExperimentalApp />
      </motion.div>
    </div>
  );
}
