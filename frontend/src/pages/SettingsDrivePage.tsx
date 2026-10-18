import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog, DialogTrigger, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useSearchParams } from "react-router";

import { ApiError, type ErrorCode } from "../api/client";
import { SPACE_LOW, bytes, useConnectDrive, useDisconnectDrive, useDrive, useDriveSpace } from "../drive/drive";
import dialogs from "../projects/projects.module.css";
import { Button } from "../ui/Button";
import { CloseButton } from "../ui/CloseButton";
import { ErrorNotice } from "../ui/ErrorNotice";
import { toast } from "../ui/Toast";
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
    if (returned.connected) toast(t("drive.connectedNow"));
  }, [returned, t]);
  useEffect(() => {
    if (params.has("resultado") || params.has("erro") || params.has("ref"))
      setParams({}, { replace: true });
  }, [params, setParams]);

  const status = drive.data;
  if (drive.error) return <ErrorNotice error={drive.error} />;
  if (!status) return <p className={styles.lead}>{t("app.loading")}</p>;
  const google = status.kind === "google" && status.writer_status !== "none";
  const expired = google && status.writer_status === "expired";

  return (
    <>
      <section className={styles.panel} aria-labelledby="drive-title">
        <h2 id="drive-title">{t("settings.drive")}</h2>
        <p className={styles.lead}>{t("drive.intro")}</p>
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
            {!expired && <Space />}
          </div>
        ) : (
          <div className={styles.conn} data-state="none">
            <strong>{t("drive.notConnected")}</strong>
            <p>
              {status.has_folder && status.account_email
                ? t("drive.notConnectedBefore", { email: status.account_email })
                : t("drive.notConnectedBody")}
            </p>
          </div>
        )}

        {status.kind !== "folder" &&
          (status.can_manage ? (
            <div className={styles.actions}>
              {(!google || expired) && (
                <Button variant="primary" onPress={() => connect.mutate(false)} isDisabled={connect.isPending}>
                  {t(expired ? "drive.reconnect" : status.has_folder ? "drive.reconnectSame" : "drive.connect")}
                </Button>
              )}
              {/* Another account: its own folder, the projects' files left behind. */}
              {status.has_folder && (
                <SwitchAccount
                  onConfirm={() => connect.mutate(true)}
                  busy={connect.isPending}
                  error={connect.error}
                  label={t(returned.error === "drive_other_account" ? "drive.switchAnyway" : "drive.switch")}
                />
              )}
              {google &&
                (confirming ? (
                  <>
                    <p>{t("drive.disconnectConfirm")}</p>
                    <Button
                      onPress={() =>
                        disconnect.mutate(undefined, {
                          onSuccess: () => toast(t("drive.disconnectedNow")),
                          onSettled: () => setConfirming(false),
                        })
                      }
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
      </section>
    </>
  );
}

/** The Google account's space, as the old site showed it: used of total, with a
 *  bar; a warning from 80% (uploads fail once Drive is full). */
function Space() {
  const { t, i18n } = useTranslation();
  const space = useDriveSpace(true);
  if (space.isPending) return null;
  if (!space.data) {
    // Its own words, plus the support code the log line carries.
    const reference = space.error instanceof ApiError ? space.error.requestId : null;
    return (
      <p className={styles.small}>
        {t("drive.spaceUnknown")}
        {reference && ` ${t("errors.reference", { id: reference })}`}
      </p>
    );
  }
  const { used, total } = space.data;
  const lang = i18n.language;
  if (total == null)
    return (
      <div className={styles.space}>
        <strong>{t("drive.space")}</strong>
        <p>{t("drive.spacePooled", { used: bytes(used, lang) })}</p>
      </div>
    );
  const share = Math.min(1, used / total);
  const low = share >= SPACE_LOW;
  return (
    <div className={styles.space} data-low={low || undefined}>
      <strong>{t("drive.space")}</strong>
      <p>
        {t("drive.spaceUsed", {
          used: bytes(used, lang),
          total: bytes(total, lang),
          percent: Math.round(share * 100),
        })}
      </p>
      <span
        className={styles.spaceBar}
        role="meter"
        aria-label={t("drive.space")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(share * 100)}
      >
        <i style={{ width: `${share * 100}%` }} />
      </span>
      {low && <p role="status">{t("drive.spaceLow")}</p>}
    </div>
  );
}

/** "Usar outra conta": the strong warning first. Nothing moves across: the new
 *  account starts with empty folders (plan section 9). */
function SwitchAccount({
  onConfirm,
  busy,
  error,
  label,
}: {
  onConfirm: () => void;
  busy: boolean;
  error: unknown; // shown here: the dialog covers the page's own notice
  label: string;
}) {
  const { t } = useTranslation();
  return (
    <DialogTrigger>
      <Button variant="ghost">{label}</Button>
      <ModalOverlay className={dialogs.overlay} isDismissable>
        <Modal className={dialogs.modal}>
          <Dialog className={dialogs.dialog} role="alertdialog">
            {({ close }) => (
              <>
                <Heading slot="title" className={dialogs.dialogTitle}>
                  {t("drive.switchTitle")}
                </Heading>
                <CloseButton onPress={close} />
                <div className={styles.switchWarning}>
                  <p>
                    <strong>{t("drive.switchWarning")}</strong>
                  </p>
                  <ul>
                    <li>{t("drive.switchFiles")}</li>
                    <li>{t("drive.switchEmpty")}</li>
                    <li>{t("drive.switchKept")}</li>
                  </ul>
                </div>
                <ErrorNotice error={error} />
                <div className={dialogs.actions}>
                  <Button variant="ghost" onPress={close}>
                    {t("drive.switchCancel")}
                  </Button>
                  <Button variant="primary" className={styles.dangerButton} onPress={onConfirm} isDisabled={busy}>
                    {t("drive.switchConfirm")}
                  </Button>
                </div>
              </>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}
