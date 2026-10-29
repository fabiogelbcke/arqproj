// The operator dashboard (/admin on Unio's own address, A38): its own small bundle.
import "../styles/global.css";
import "../ui/sizes.css";
import "../i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { applyStoredTheme } from "../ui/theme";
import { AdminApp } from "./AdminApp";
import { OfficeSignupApp, SIGNUP_PATH } from "./OfficeSignup";

applyStoredTheme();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* The same bundle serves the link to create an office, for no operator. */}
    {window.location.pathname === SIGNUP_PATH ? <OfficeSignupApp /> : <AdminApp />}
  </StrictMode>,
);
