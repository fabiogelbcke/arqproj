import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { createBrowserRouter, Link, Outlet, RouterProvider, useParams } from "react-router";

import { ApiError, api, call, setCsrfToken, type Schemas } from "../api/client";
import { Button } from "../ui/Button";
import { EmailField } from "../ui/EmailField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { UnioMark } from "../ui/UnioMark";
import { officeErrorsUrl, SUPPORT_CODE, supportCodeUrl, type LogsTarget } from "./logs";
import styles from "./admin.module.css";

type Operator = Schemas["OperatorOut"];
type Office = Schemas["AdminOfficeOut"];

const ME = ["admin", "me"] as const;

/** The operator signed in, or null (401). */
function useOperator() {
  return useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        const me = await call(api.GET("/api/admin/me"));
        setCsrfToken(me.csrf_token);
        return me;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });
}

function target(me: Operator): LogsTarget | null {
  return me.logs_project && me.logs_service ? { project: me.logs_project, service: me.logs_service } : null;
}

const dateTime = (value: string | null | undefined, locale: string) =>
  value ? new Date(value).toLocaleString(locale, { dateStyle: "short", timeStyle: "short" }) : "—";
const date = (value: string, locale: string) => new Date(value).toLocaleDateString(locale, { dateStyle: "short" });

/** "Entrar com Google", and why the last try didn't get in (?entrar=…). Locally,
 *  where Google can't be reached, an allowlisted email signs in directly. */
function SignIn() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const problem = new URLSearchParams(window.location.search).get("entrar");
  const [email, setEmail] = useState("");
  const google = useMutation({
    mutationFn: () => call(api.POST("/api/admin/signin")),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const local = useMutation({
    mutationFn: () => call(api.POST("/api/admin/dev-session", { body: { email } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ME }),
  });
  return (
    <main className={styles.centered}>
      <div className={styles.signIn}>
        <UnioMark className={styles.signInMark} />
        <h1>{t("admin.title")}</h1>
        <p className={styles.muted}>{t("admin.signInIntro")}</p>
        {problem && (
          <p role="alert" className={styles.problem}>
            {t(`admin.signInProblem.${problem}`, { defaultValue: t("admin.signInProblem.falhou") })}
          </p>
        )}
        <Button variant="primary" onPress={() => google.mutate()} isDisabled={google.isPending}>
          {t("admin.signInGoogle")}
        </Button>
        <ErrorNotice error={google.error} />
        {/* Never deployed (the server refuses it there too): a local address only. */}
        {window.location.hostname === "localhost" && (
          <Form
            className={styles.devForm}
            onSubmit={(event) => {
              event.preventDefault();
              local.mutate();
            }}
          >
            <EmailField label={t("admin.devSignIn")} value={email} onChange={setEmail} isRequired lookup />
            <Button type="submit" isDisabled={local.isPending}>
              {t("admin.devSignInSubmit")}
            </Button>
            <ErrorNotice error={local.error} />
          </Form>
        )}
      </div>
    </main>
  );
}

/** The bar on every page: Unio, the operator, Sair. */
function Layout({ me }: { me: Operator }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const signOut = useMutation({
    mutationFn: () => call(api.POST("/api/admin/signout")),
    onSuccess: () => {
      setCsrfToken(null);
      client.setQueryData(ME, null);
    },
  });
  return (
    <>
      <header className={styles.bar}>
        <Link to="/" className={styles.brand}>
          <UnioMark className={styles.barMark} />
          <span>{t("admin.title")}</span>
        </Link>
        <span className={styles.muted}>{me.email}</span>
        <Button size="small" variant="ghost" onPress={() => signOut.mutate()} isDisabled={signOut.isPending}>
          {t("nav.signOut")}
        </Button>
      </header>
      <main className={styles.main}>
        <ErrorNotice error={signOut.error} />
        <Outlet context={me} />
      </main>
    </>
  );
}

/** A support code from a client's error screen → its log lines. */
function SupportLookup({ me }: { me: Operator }) {
  const { t } = useTranslation();
  const [code, setCode] = useState("");
  const logs = target(me);
  const valid = SUPPORT_CODE.test(code.trim());
  return (
    <section className={styles.panel} aria-labelledby="support">
      <h2 id="support">{t("admin.support")}</h2>
      <p className={styles.muted}>{t("admin.supportIntro")}</p>
      <Form
        className={styles.supportForm}
        onSubmit={(event) => {
          event.preventDefault();
          if (logs && valid) window.open(supportCodeUrl(logs, code), "_blank", "noopener");
        }}
      >
        <TextField
          label={t("admin.supportCode")}
          value={code}
          onChange={setCode}
          validate={(value) => (value && !SUPPORT_CODE.test(value.trim()) ? t("admin.supportInvalid") : null)}
        />
        <Button type="submit" isDisabled={!logs || !valid}>
          {t("admin.supportOpen")}
        </Button>
      </Form>
      {!logs && <p className={styles.muted}>{t("admin.logsOnlyDeployed")}</p>}
    </section>
  );
}

function StorageState({ office }: { office: Office }) {
  const { t } = useTranslation();
  const state =
    office.storage === "google"
      ? office.writer_status === "connected"
        ? office.reader_status === "no_access"
          ? "unreadable"
          : "connected"
        : office.writer_status === "expired"
          ? "expired"
          : "disconnected"
      : office.storage;
  return <span className={styles.state} data-state={state}>{t(`admin.storage.${state}`)}</span>;
}

function Offices() {
  const { t, i18n } = useTranslation();
  const { data: me } = useOperator();
  const offices = useQuery({ queryKey: ["admin", "offices"], queryFn: () => call(api.GET("/api/admin/offices")) });
  return (
    <>
      <div className={styles.head}>
        <h1>{t("admin.offices")}</h1>
        {offices.data && <span className={styles.count}>{offices.data.length}</span>}
      </div>
      {me && <SupportLookup me={me} />}
      <ErrorNotice error={offices.error} />
      {offices.data && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t("admin.office")}</th>
                <th>{t("admin.team")}</th>
                <th>{t("admin.projects")}</th>
                <th>{t("admin.storageTitle")}</th>
                <th>{t("admin.lastActivity")}</th>
                <th>{t("admin.emails")}</th>
                <th>{t("admin.links")}</th>
              </tr>
            </thead>
            <tbody>
              {offices.data.map((office) => (
                <tr key={office.slug}>
                  <td>
                    <Link to={`/escritorios/${office.slug}`} className={styles.officeName}>
                      {office.name}
                    </Link>
                    <span className={styles.muted}>{office.hosts[0] ?? office.slug}</span>
                    {office.status !== "active" && <span className={styles.state}>{t(`admin.status.${office.status}`)}</span>}
                  </td>
                  <td>
                    {t("admin.teamCount", { count: office.staff })}
                    {office.pending > 0 && <span className={styles.muted}>{t("admin.pending", { count: office.pending })}</span>}
                  </td>
                  <td>
                    {t("admin.activeCount", { count: office.projects.active ?? 0 })}
                    <span className={styles.muted}>
                      {t("admin.otherProjects", {
                        completed: office.projects.completed ?? 0,
                        archived: office.projects.archived ?? 0,
                      })}
                    </span>
                  </td>
                  <td>
                    <StorageState office={office} />
                  </td>
                  <td>{dateTime(office.last_activity_at, i18n.language)}</td>
                  <td>{office.emails_sent}</td>
                  <td>
                    {office.share_links}
                    <span className={styles.muted}>{t("admin.downloads", { count: office.downloads })}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.fact}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function OfficePage() {
  const { t, i18n } = useTranslation();
  const { slug = "" } = useParams();
  const { data: me } = useOperator();
  const office = useQuery({
    queryKey: ["admin", "office", slug],
    queryFn: () => call(api.GET("/api/admin/offices/{slug}", { params: { path: { slug } } })),
  });
  const logs = me ? target(me) : null;
  if (office.error) return <ErrorNotice error={office.error} />;
  if (!office.data) return <p className={styles.muted}>{t("app.loading")}</p>;
  const o = office.data;
  return (
    <>
      <Link to="/" className={styles.back}>
        ← {t("admin.offices")}
      </Link>
      <div className={styles.head}>
        <h1>{o.name}</h1>
        <span className={styles.state} data-state={o.status}>
          {t(`admin.status.${o.status}`)}
        </span>
      </div>
      <p className={styles.hosts}>
        {o.hosts.map((host) => (
          <a key={host} href={`https://${host}/painel/`} target="_blank" rel="noreferrer">
            {host}
          </a>
        ))}
      </p>
      <dl className={styles.facts}>
        <Fact label={t("admin.created")}>{date(o.created_at, i18n.language)}</Fact>
        <Fact label={t("admin.team")}>
          {t("admin.teamCount", { count: o.staff })} · {t("admin.owners", { count: o.owners })}
        </Fact>
        <Fact label={t("admin.projects")}>
          {t("admin.activeCount", { count: o.projects.active ?? 0 })} ·{" "}
          {t("admin.otherProjects", { completed: o.projects.completed ?? 0, archived: o.projects.archived ?? 0 })}
        </Fact>
        <Fact label={t("admin.storageTitle")}>
          <StorageState office={o} />
          {o.drive_account && <span className={styles.muted}>{o.drive_account}</span>}
        </Fact>
        <Fact label={t("admin.lastActivity")}>{dateTime(o.last_activity_at, i18n.language)}</Fact>
        <Fact label={t("admin.emails")}>{o.emails_sent}</Fact>
        <Fact label={t("admin.links")}>
          {o.share_links} · {t("admin.downloads", { count: o.downloads })}
        </Fact>
      </dl>
      <section className={styles.panel} aria-labelledby="errors">
        <h2 id="errors">{t("admin.errors")}</h2>
        {logs ? (
          <a href={officeErrorsUrl(logs, o.slug)} target="_blank" rel="noreferrer">
            {t("admin.errorsOpen")}
          </a>
        ) : (
          <p className={styles.muted}>{t("admin.logsOnlyDeployed")}</p>
        )}
      </section>
      <section aria-labelledby="team">
        <h2 id="team">{t("admin.team")}</h2>
        {o.team.length === 0 && <p className={styles.muted}>{t("admin.noTeam")}</p>}
        <div className={styles.tableWrap} hidden={o.team.length === 0}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t("admin.who")}</th>
                <th>{t("admin.role")}</th>
                <th>{t("admin.state")}</th>
                <th>{t("admin.lastSeen")}</th>
              </tr>
            </thead>
            <tbody>
              {o.team.map((person) => (
                <tr key={person.email}>
                  <td>
                    {person.name}
                    <span className={styles.muted}>{person.email}</span>
                  </td>
                  <td>{t(`team.role.${person.role}`)}</td>
                  <td>{t(`admin.personStatus.${person.status}`)}</td>
                  <td>{dateTime(person.last_seen_at, i18n.language)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function Root() {
  const { t } = useTranslation();
  const me = useOperator();
  if (me.isPending) return <p className={styles.centered}>{t("app.loading")}</p>;
  if (me.error)
    return (
      <main className={styles.centered}>
        <ErrorNotice error={me.error} />
      </main>
    );
  if (!me.data) return <SignIn />;
  return <Layout me={me.data} />;
}

export const adminRoutes = [
  {
    element: <Root />,
    children: [
      { index: true, element: <Offices /> },
      { path: "escritorios/:slug", element: <OfficePage /> },
    ],
  },
];

export function AdminApp() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } }));
  const [router] = useState(() => createBrowserRouter(adminRoutes, { basename: "/admin" }));
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
