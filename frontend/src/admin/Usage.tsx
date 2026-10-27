import { useMutation } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api, call, type Schemas } from "../api/client";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { InfoTip } from "../ui/InfoTip";
import { Panel } from "../ui/Panel";
import styles from "./admin.module.css";

// Verified in the connected PostHog project: the backend events dashboard.
const DASHBOARD = "https://us.posthog.com/project/682597/dashboard/2259460";
export function analyticsUrl(slug?: string) {
  const url = new URL(DASHBOARD);
  if (slug) url.searchParams.set("properties", JSON.stringify([{ key: "tenant", value: [slug], operator: "exact", type: "event" }]));
  return url.toString();
}

/** PostHog, as a secondary action in a page's header. */
export function AnalyticsLink({ slug }: { slug?: string }) {
  const { t } = useTranslation();
  return (
    <a className={styles.headLink} href={analyticsUrl(slug)} target="_blank" rel="noreferrer">
      {t(slug ? "admin.analyticsTenant" : "admin.analytics")} <span aria-hidden="true">↗</span>
    </a>
  );
}

function bytes(value: number, locale: string) {
  const unit = value >= 1024 ** 3 ? "GiB" : value >= 1024 ** 2 ? "MiB" : "KiB";
  const divisor = unit === "GiB" ? 1024 ** 3 : unit === "MiB" ? 1024 ** 2 : 1024;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / divisor)} ${unit}`;
}

/** A small figure: its label over its value, several to a row. */
function Figure({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className={styles.figure}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** How the office uses the product, from what is saved: a compact list. The
 *  project count is in the summary above, so it is not repeated here. */
export function Usage({ office }: { office: Schemas["AdminOfficeOut"] }) {
  const { t } = useTranslation();
  const usage = Object.entries(office.usage ?? {}).filter(([key]) => key !== "projects");
  return (
    <Panel aria-labelledby="usage">
      <h2 id="usage">{t("admin.usageTitle")}</h2>
      <dl className={styles.figures}>
        {usage.map(([key, value]) => (
          <Figure key={key} label={t(`admin.usage.${key}`)}>
            {key === "logo" ? t(value ? "admin.yes" : "admin.no") : value}
          </Figure>
        ))}
      </dl>
    </Panel>
  );
}

/** File statistics, read from storage only when asked (never saved). */
export function FileStatistics({ office }: { office: Schemas["AdminOfficeOut"] }) {
  const { t, i18n } = useTranslation();
  const files = useMutation({ mutationFn: () => call(api.POST("/api/admin/offices/{slug}/file-statistics", { params: { path: { slug: office.slug } } })) });
  const data = files.data;
  return (
    <Panel aria-labelledby="files">
      <div className={styles.panelHead}>
        <h2 id="files">{t("admin.fileStats")}</h2>
        <InfoTip label={t("admin.aboutFiles")}>{t("admin.fileStatsScope")}</InfoTip>
        <Button size="small" className={styles.panelAction} onPress={() => files.mutate()} isDisabled={files.isPending || office.storage === "none"}>
          {t(files.isPending ? "app.loading" : data ? "admin.reloadFiles" : "admin.loadFiles")}
        </Button>
      </div>
      <ErrorNotice error={files.error} />
      {data && !files.error && (
        <div className={styles.stack} aria-live="polite">
          <p className={styles.muted}>{t("admin.loadedAt", { time: new Date(data.loaded_at).toLocaleString(i18n.language) })}</p>
          <dl className={styles.figures}>
            <Figure label={t("admin.fileCount")}>{data.files}</Figure>
            <Figure label={t("admin.fileBytes")}>{bytes(data.known_bytes, i18n.language)}</Figure>
            <Figure label={t("admin.unknownSizes")}>{data.unknown_sizes}</Figure>
            <Figure label={t("admin.projectsWithFiles")}>{t("admin.projectsOf", { populated: data.projects_with_files, projects: data.projects })}</Figure>
            <Figure label={<>{t("admin.accountSpace")} <InfoTip label={t("admin.aboutAccount")}>{t("admin.accountSpaceMeaning")}</InfoTip></>}>
              {data.account_used == null ? t("admin.unavailable") : bytes(data.account_used, i18n.language)}
              {data.account_limit != null && ` / ${bytes(data.account_limit, i18n.language)}`}
            </Figure>
          </dl>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr><th>{t("admin.fileType")}</th><th>{t("admin.fileCount")}</th><th>{t("admin.fileBytes")}</th><th>{t("admin.unknownSizes")}</th></tr>
              </thead>
              <tbody>
                {data.types.map((row) => (
                  <tr key={row.kind}>
                    <td>{t(`admin.fileKinds.${row.kind}`, { defaultValue: row.kind.toUpperCase() })}</td>
                    <td>{row.files}</td>
                    <td>{bytes(row.known_bytes, i18n.language)}</td>
                    <td>{row.unknown_sizes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Panel>
  );
}
