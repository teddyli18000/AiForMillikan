import { motion } from "framer-motion";
import { NormalWorkspace } from "./components/normal/NormalWorkspace";
import "./styles/app.css";

export default function App() {
  return (
    <div className="app-shell">
      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.48 }}>
        <NormalWorkspace />
      </motion.div>
    </div>
  );
}
