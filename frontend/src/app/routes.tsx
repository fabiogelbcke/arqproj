import { I18nProvider } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, type RouteObject } from "react-router";

import { type Locale, useOfficeLocale } from "../i18n";
import { ChoosePasswordPage } from "../pages/ChoosePasswordPage";
import { ForgotPasswordPage } from "../pages/ForgotPasswordPage";
import { JoinPage } from "../pages/JoinPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { SettingsDrivePage } from "../pages/SettingsDrivePage";
import { SettingsLayout } from "../pages/SettingsLayout";
import { SettingsOfficePage } from "../pages/SettingsOfficePage";
import { SettingsTeamPage } from "../pages/SettingsTeamPage";
import { SignInPage } from "../pages/SignInPage";
import { useMe, useTenant } from "../session/session";
import { Toaster } from "../ui/Toast";
import { UpdateBanner } from "../ui/UpdateBanner";
import { SignedInLayout } from "./SignedInLayout";

/** The office's language, known before sign-in from /api/tenant. */
function Root() {
  const tenant = useTenant();
  const me = useMe();
  useOfficeLocale((me.data?.tenant_locale ?? tenant.data?.locale) as Locale | undefined);
  const { i18n } = useTranslation();
  return (
    <I18nProvider locale={i18n.language}>
      <Outlet />
      <UpdateBanner />
      <Toaster />
    </I18nProvider>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: "entrar", element: <SignInPage /> },
      { path: "definir-senha", element: <ChoosePasswordPage /> },
      { path: "esqueci-a-senha", element: <ForgotPasswordPage /> },
      { path: "entrar-na-equipe", element: <JoinPage /> },
      {
        element: <SignedInLayout />,
        children: [
          { index: true, element: <ProjectsPage /> },
          {
            path: "configuracoes",
            element: <SettingsLayout />,
            children: [
              { index: true, element: <Navigate to="/configuracoes/escritorio" replace /> },
              { path: "escritorio", element: <SettingsOfficePage /> },
              { path: "drive", element: <SettingsDrivePage /> },
              { path: "equipe", element: <SettingsTeamPage /> },
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

