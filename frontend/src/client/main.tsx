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
import { shareToken } from "./shareToken";
import { EXAMPLE_SLUG } from "./example/address";
import { applyStoredTheme } from "../ui/theme";

// The example project (plan section 16), loaded only at its address.
const ExampleApp = lazy(() => import("./example/ExampleApp").then((m) => ({ default: m.ExampleApp })));
// The files someone shared by link (A37), at `/share/{token}`.
const SharePage = lazy(() => import("./SharePage").then((m) => ({ default: m.SharePage })));
const token = shareToken(window.location.pathname);

applyStoredTheme();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {token ? (
      <Suspense fallback={null}>
        <SharePage token={token} />
      </Suspense>
    ) : slugFromPath(window.location.pathname) === EXAMPLE_SLUG ? (
      <Suspense fallback={null}>
        <ExampleApp />
      </Suspense>
    ) : (
      <ClientApp />
    )}
  </StrictMode>,
);
