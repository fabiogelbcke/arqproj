// The preview page (/painel/previa): its own small bundle, with the client page's
// styles, since it draws the client page (plan section 18, "Visual variants").
import "../../ui/sizes.css";
import "../prototype.css";
import "../page.css";
// The same shared values and redesigned page as the client page (client/main.tsx).
import "../../styles/tokens.css";
import "../project.css";
import "./preview.css";
import "../../i18n";
import "../../posthog";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { PreviewApp, PreviewFrame } from "./PreviewApp";

const framed = new URLSearchParams(window.location.search).has("frame");
createRoot(document.getElementById("root")!).render(
  <StrictMode>{framed ? <PreviewFrame /> : <PreviewApp />}</StrictMode>,
);
