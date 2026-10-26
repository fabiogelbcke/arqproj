import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, call, type Schemas } from "../api/client";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import styles from "./admin.module.css";

// Verified in the connected PostHog project: the backend events dashboard.
const DASHBOARD = "https://us.posthog.com/project/682597/dashboard/2259460";
export function analyticsUrl(slug?: string) {
  const url = new URL(DASHBOARD);
  if (slug) url.searchParams.set("properties", JSON.stringify([{ key: "tenant", value: [slug], operator: "exact", type: "event" }]));
  return url.toString();
}

export function AnalyticsLink({ slug }: { slug?: string }) {
  const { t } = useTranslation();
  return <a href={analyticsUrl(slug)} target="_blank" rel="noreferrer">{t(slug ? "admin.analyticsTenant" : "admin.analytics")}</a>;
}

function bytes(value: number, locale: string) {
  const unit = value >= 1024 ** 3 ? "GiB" : value >= 1024 ** 2 ? "MiB" : "KiB";
  const divisor = unit === "GiB" ? 1024 ** 3 : unit === "MiB" ? 1024 ** 2 : 1024;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / divisor)} ${unit}`;
}

export function Usage({ office }: { office: Schemas["AdminOfficeOut"] }) {
  const { t, i18n } = useTranslation();
  const files = useMutation({ mutationFn: () => call(api.POST("/api/admin/offices/{slug}/file-statistics", { params: { path: { slug: office.slug } } })) });
  const data = files.data;
  return <>
    <section className={styles.panel}>
      <h2>{t("admin.usageTitle")}</h2>
      <dl className={styles.facts}>
        {Object.entries(office.usage ?? {}).map(([key, value]) => <div className={styles.fact} key={key}><dt>{t(`admin.usage.${key}`)}</dt><dd>{key === "logo" ? t(value ? "admin.yes" : "admin.no") : value}</dd></div>)}
      </dl>
      <p>{t("admin.linkStates", { ...office.link_statuses })}</p>
      <p className={styles.muted}>{t("admin.downloadMeaning")}</p>
      <AnalyticsLink slug={office.slug} />
    </section>
    <section className={styles.panel}>
      <h2>{t("admin.fileStats")}</h2>
      <p className={styles.muted}>{t("admin.fileStatsScope")}</p>
      <Button onPress={() => files.mutate()} isDisabled={files.isPending || office.storage === "none"}>{t(files.isPending ? "app.loading" : data ? "admin.reloadFiles" : "admin.loadFiles")}</Button>
      <ErrorNotice error={files.error} />
      {data && !files.error && <div aria-live="polite">
        <p className={styles.muted}>{t("admin.loadedAt", { time: new Date(data.loaded_at).toLocaleString(i18n.language) })}</p>
        <p>{t("admin.fileTotals", { files: data.files, populated: data.projects_with_files, projects: data.projects, size: bytes(data.known_bytes, i18n.language), unknown: data.unknown_sizes })}</p>
        <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>{t("admin.fileType")}</th><th>{t("admin.fileCount")}</th><th>{t("admin.fileBytes")}</th><th>{t("admin.unknownSizes")}</th></tr></thead><tbody>
          {data.types.map(row => <tr key={row.kind}><td>{t(`admin.fileKinds.${row.kind}`, { defaultValue: row.kind.toUpperCase() })}</td><td>{row.files}</td><td>{bytes(row.known_bytes, i18n.language)}</td><td>{row.unknown_sizes}</td></tr>)}
        </tbody></table></div>
        <p>{t("admin.accountSpace")}: {data.account_used == null ? t("admin.unavailable") : bytes(data.account_used, i18n.language)}{data.account_limit != null && ` / ${bytes(data.account_limit, i18n.language)}`}</p>
        <p className={styles.muted}>{t("admin.accountSpaceMeaning")}</p>
      </div>}
    </section>
  </>;
}
