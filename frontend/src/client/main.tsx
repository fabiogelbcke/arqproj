// The client's project page (/{slug}): its own small bundle (A20 revised).
import "../ui/sizes.css";
import "./prototype.css";
import "./page.css";
// The site's shared design values, then the redesigned page (22 Oct 2026), both
// after the older stylesheets so they win where they meet.
import "../styles/tokens.css";
import "./project.css";
import "../i18n";

import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";

import { ClientApp, slugFromPath } from "./ClientApp";
import { EXAMPLE_SLUG } from "./example/address";
import { applyStoredTheme } from "../ui/theme";

// The example project (plan section 16), loaded only at its address.
const ExampleApp = lazy(() => import("./example/ExampleApp").then((m) => ({ default: m.ExampleApp })));

applyStoredTheme();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {slugFromPath(window.location.pathname) === EXAMPLE_SLUG ? (
      <Suspense fallback={null}>
        <ExampleApp />
      </Suspense>
    ) : (
      <ClientApp />
    )}
  </StrictMode>,
);
