import { I18nProvider } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, type RouteObject } from "react-router";

import { type Locale, useOfficeLocale } from "../i18n";
import { ChoosePasswordPage } from "../pages/ChoosePasswordPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { SettingsDrivePage } from "../pages/SettingsDrivePage";
import { SettingsLayout } from "../pages/SettingsLayout";
import { SettingsOfficePage } from "../pages/SettingsOfficePage";
import { SignInPage } from "../pages/SignInPage";
import { useMe, useTenant } from "../session/session";
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
    </I18nProvider>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: "entrar", element: <SignInPage /> },
      { path: "definir-senha", element: <ChoosePasswordPage /> },
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
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

