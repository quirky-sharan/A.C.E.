import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/orbitron/latin-600.css";
import "./styles/index.css";

import { MotionConfig } from "motion/react";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";

// Fonts are bundled with the app (no CDN; all SIL OFL 1.1). MotionConfig follows the Windows
// "animation effects" setting (prefers-reduced-motion, §14.4, NFR-10).
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </React.StrictMode>,
);
