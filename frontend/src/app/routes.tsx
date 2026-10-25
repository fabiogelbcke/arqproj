import { I18nProvider } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, type RouteObject } from "react-router";

import { type Locale, useOfficeLocale } from "../i18n";
import { ChoosePasswordPage } from "../pages/ChoosePasswordPage";
import { ConfirmLinkPage } from "../pages/ConfirmEmailPage";
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
import { usePageTitle, type TitleHandle } from "./pageTitle";
import { SignedInLayout } from "./SignedInLayout";

/** The office's language, known before sign-in from /api/tenant. */
function Root() {
  const tenant = useTenant();
  const me = useMe();
  useOfficeLocale((me.data?.tenant_locale ?? tenant.data?.locale) as Locale | undefined);
  usePageTitle(me.data?.tenant_name ?? tenant.data?.name);
  const { i18n } = useTranslation();
  return (
    <I18nProvider locale={i18n.language}>
      <Outlet />
      <UpdateBanner />
      <Toaster />
    </I18nProvider>
  );
}

const title = (...keys: string[]): TitleHandle => ({ title: keys });

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: "entrar", element: <SignInPage />, handle: title("signIn.title") },
      { path: "definir-senha", element: <ChoosePasswordPage />, handle: title("choosePassword.pageTitle") }, // invite, reset or spent link alike
      { path: "esqueci-a-senha", element: <ForgotPasswordPage />, handle: title("forgot.title") },
      { path: "entrar-na-equipe", element: <JoinPage />, handle: title("join.pageTitle") },
      { path: "confirmar-email", element: <ConfirmLinkPage />, handle: title("confirmEmail.pageTitle") },
      {
        element: <SignedInLayout />,
        children: [
          { index: true, element: <ProjectsPage />, handle: title("nav.projects") },
          {
            path: "configuracoes",
            element: <SettingsLayout />,
            children: [
              { index: true, element: <Navigate to="/configuracoes/escritorio" replace /> },
              { path: "escritorio", element: <SettingsOfficePage />, handle: title("settings.office", "settings.title") },
              { path: "drive", element: <SettingsDrivePage />, handle: title("settings.drive", "settings.title") },
              { path: "equipe", element: <SettingsTeamPage />, handle: title("settings.team", "settings.title") },
            ],
          },
          { path: "*", element: <NotFoundPage />, handle: title("notFound.title") },
        ],
      },
    ],
  },
];

