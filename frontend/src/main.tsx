import "./styles/global.css";
import "./ui/sizes.css";
import "./i18n";
import "./posthog";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { applyStoredTheme } from "./ui/theme";

applyStoredTheme();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
