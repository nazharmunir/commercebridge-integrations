import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import LiveDashboard from "./LiveDashboard";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LiveDashboard />
  </StrictMode>,
);
