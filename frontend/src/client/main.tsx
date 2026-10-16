// The client's project page (/{slug}): its own small bundle (A20 revised).
import "./prototype.css";
import "./page.css";
import "../i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ClientApp } from "./ClientApp";
import { applyStoredTheme } from "./ProjectPage";

applyStoredTheme();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClientApp />
  </StrictMode>,
);
