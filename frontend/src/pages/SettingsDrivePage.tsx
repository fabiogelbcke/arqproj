import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { ApiError, type ErrorCode } from "../api/client";
import { useConnectDrive, useDisconnectDrive, useDrive } from "../drive/drive";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import styles from "./pages.module.css";

export function SettingsDrivePage() {
  const { t } = useTranslation();
  const drive = useDrive();
  const connect = useConnectDrive();
  const disconnect = useDisconnectDrive();
  const [confirming, setConfirming] = useState(false);
  const [params, setParams] = useSearchParams();
  // Google brings the person back with ?resultado=conectado or ?erro=<code>.
  const [returned] = useState(() => ({
    connected: params.get("resultado") === "conectado",
    error: params.get("erro"),
    reference: params.get("ref"),
  }));
  useEffect(() => {
    if (params.has("resultado") || params.has("erro") || params.has("ref"))
      setParams({}, { replace: true });
  }, [params, setParams]);

  const status = drive.data;
  if (!status) return <p className={styles.lead}>{t("app.loading")}</p>;
  const google = status.kind === "google" && status.writer_status !== "none";
  const expired = google && status.writer_status === "expired";

  return (
    <>
      <h1 className={styles.display}>{t("settings.title")}</h1>
      <section className={styles.panel} aria-labelledby="drive-title">
        <h2 id="drive-title">{t("settings.drive")}</h2>
        <p className={styles.lead}>{t("drive.intro")}</p>
        {returned.connected && <p role="status">{t("drive.connectedNow")}</p>}
        {returned.error && (
          <ErrorNotice
            error={new ApiError(returned.error as ErrorCode, undefined, returned.reference)}
          />
        )}

        {status.kind === "folder" ? (
          <div className={styles.conn} data-state="ok">
            <strong>{t("drive.local")}</strong>
            <p>{t("drive.localBody")}</p>
          </div>
        ) : google ? (
          <div className={styles.conn} data-state={expired ? "expired" : "ok"}>
            <strong>{t(expired ? "drive.expired" : "drive.connected")}</strong>
            {status.account_email && <p>{t("drive.connectedAs", { email: status.account_email })}</p>}
            {expired && <p>{t("drive.expiredBody")}</p>}
            {status.reader_status === "no_access" && <p>{t("drive.readerProblem")}</p>}
            {status.folder_url && (
              <a href={status.folder_url} target="_blank" rel="noopener noreferrer">
                {t("drive.openFolder")}
              </a>
            )}
          </div>
        ) : (
          <div className={styles.conn} data-state="none">
            <strong>{t("drive.notConnected")}</strong>
            <p>{t("drive.notConnectedBody")}</p>
          </div>
        )}

        {status.kind !== "folder" &&
          (status.can_manage ? (
            <div className={styles.actions}>
              {(!google || expired) && (
                <Button variant="primary" onPress={() => connect.mutate()} isDisabled={connect.isPending}>
                  {t(expired ? "drive.reconnect" : "drive.connect")}
                </Button>
              )}
              {google &&
                (confirming ? (
                  <>
                    <p>{t("drive.disconnectConfirm")}</p>
                    <Button
                      onPress={() => disconnect.mutate(undefined, { onSettled: () => setConfirming(false) })}
                      isDisabled={disconnect.isPending}
                    >
                      {t("drive.disconnect")}
                    </Button>
                  </>
                ) : (
                  <Button variant="ghost" onPress={() => setConfirming(true)}>
                    {t("drive.disconnect")}
                  </Button>
                ))}
            </div>
          ) : (
            <p className={styles.small}>{t("drive.ownerOnly")}</p>
          ))}
        <ErrorNotice error={connect.error ?? disconnect.error} />
        {disconnect.isSuccess && <p role="status">{t("drive.disconnectedNow")}</p>}
      </section>
    </>
  );
}
