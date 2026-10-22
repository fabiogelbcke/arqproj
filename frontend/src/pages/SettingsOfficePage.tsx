import { useState } from "react";
import { FileTrigger, Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { LIMITS } from "../api/limits";
import { useConnectDrive, useDrive } from "../drive/drive";
import { useDarkLogo, useOffice, useSaveOffice, useUploadLogo } from "../office/office";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { ImageCropDialog } from "../ui/ImageCropDialog";
import { EmailField } from "../ui/EmailField";
import { Panel } from "../ui/Panel";
import { TextField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import styles from "./pages.module.css";

/** "ALINEA ARQUITETOS" → "AA"; "Estúdio Norte (dev)" → "EN". */
export function initials(name: string): string {
  const words = name.replace(/\(.*?\)/g, "").trim().split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => word[0]!.toLocaleUpperCase("pt-BR"))
    .join("");
}

export function SettingsOfficePage() {
  const { t } = useTranslation();
  return (
    <Panel className={styles.settingsPanel} aria-labelledby="office-title">
      <h2 id="office-title" className="sr-only">
        {t("settings.office")}
      </h2>
      <OfficeDetails />
    </Panel>
  );
}

/** The office's name, contact email and logo: Configurações › Escritório, and the
 *  first steps' dialog (`onSaved` closes it once the name and email are saved). */
export function OfficeDetails({ onSaved }: { onSaved?: () => void }) {
  const { t } = useTranslation();
  const office = useOffice();
  const drive = useDrive();
  const save = useSaveOffice();
  const logo = useUploadLogo();
  const darkLogo = useDarkLogo();
  // The image being cropped before it goes up, as a local address.
  const [cropping, setCropping] = useState<{ source: string; dark: boolean } | null>(null);
  const stopCropping = () => {
    if (cropping) URL.revokeObjectURL(cropping.source);
    setCropping(null);
  };
  // "Usar o mesmo logo no modo escuro" unticked, before a dark mode logo is chosen.
  const [wantsDark, setWantsDark] = useState(false);
  const [draft, setDraft] = useState<{ name: string; contact_email: string } | null>(null);

  if (office.error) return <ErrorNotice error={office.error} />;
  if (!office.data) return <p className={styles.lead}>{t("app.loading")}</p>;
  const details = office.data;
  const values = draft ?? { name: details.name, contact_email: details.contact_email ?? "" };
  const manage = details.can_manage;
  const separateDark = wantsDark || !!details.logo_dark_url;
  // The logo lives in the office's storage: Google Drive connected, or local folders.
  // On Drive, both paths must work: the office's grant writes it, the reader shows it.
  const storageReady =
    drive.data?.kind === "folder" ||
    (drive.data?.kind === "google" &&
      drive.data.writer_status === "connected" &&
      drive.data.reader_status === "ok");

  return (
    <>
      {!manage && <p className={styles.small}>{t("office.ownerOnly")}</p>}
      <Form
        onSubmit={(event) => {
          event.preventDefault();
          const submitted = values;
          // Keep anything typed while the save was on its way.
          save.mutate(submitted, {
            onSuccess: () => {
              setDraft((current) => (current === submitted ? null : current));
              toast(t("office.saved"));
              onSaved?.();
            },
          });
        }}
        className={styles.form}
      >
        <TextField
          label={t("office.name")}
          description={t("office.nameHint")}
          value={values.name}
          onChange={(name) => setDraft({ ...values, name })}
          isRequired
          maxLength={LIMITS.officeName}
          isReadOnly={!manage}
        />
        <EmailField
          label={t("office.email")}
          description={t("office.emailHint")}
          value={values.contact_email}
          onChange={(contact_email) => setDraft({ ...values, contact_email })}
          isReadOnly={!manage}
        />
        <ErrorNotice error={save.error} />
        {manage && (
          <div className={styles.actions}>
            <Button type="submit" variant="primary" isDisabled={save.isPending || !draft}>
              {t("office.save")}
            </Button>
          </div>
        )}
      </Form>

      <div className={styles.logoBlock}>
        <h3>{t("office.logo")}</h3>
        {/* Without the office's storage there is nowhere to keep a logo: say so
            first, with the way to connect, rather than an empty slot and its specs. */}
        {manage && !storageReady && (drive.data ? <NeedsDrive /> : <ErrorNotice error={drive.error} />)}
        {details.logo_url ? (
          <img className={styles.logo} src={details.logo_url} alt={t("office.logoAlt", { name: details.name })} />
        ) : (
          (storageReady || !manage) && (
            // An empty slot with the office's initials until a logo is uploaded.
            <div className={styles.logoEmpty} role="img" aria-label={t("office.logoNone")}>
              <span aria-hidden="true">{initials(details.name)}</span>
              <small>{t("office.logoNone")}</small>
            </div>
          )
        )}
        {manage && storageReady && (
          <>
            <p className={styles.small}>{t("office.logoHint")}</p>
            <ChooseImage label={t("office.chooseLogo")} onChosen={(source) => setCropping({ source, dark: false })} />
          </>
        )}
      </div>

      {details.logo_url && (manage || details.logo_dark_url) && (
        <div className={styles.logoBlock}>
          {manage && (
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={!separateDark}
                disabled={darkLogo.isPending}
                onChange={(event) => {
                  if (!event.target.checked) return setWantsDark(true);
                  setWantsDark(false);
                  // Back to one logo: the dark mode one goes.
                  if (details.logo_dark_url)
                    darkLogo.mutate(null, {
                      onSuccess: () => toast(t("office.darkLogoRemoved")),
                      onError: (error) => toastError(error),
                    });
                }}
              />
              {t("office.darkSame")}
            </label>
          )}
          {separateDark && (
            <>
              <h3>{t("office.darkLogo")}</h3>
              {details.logo_dark_url ? (
                <img
                  className={`${styles.logo} ${styles.logoOnDark}`}
                  src={details.logo_dark_url}
                  alt={t("office.logoAlt", { name: details.name })}
                />
              ) : (
                <div className={`${styles.logoEmpty} ${styles.logoOnDark}`} aria-hidden="true" />
              )}
              <p className={styles.small}>{t("office.darkHint")}</p>
              {manage && storageReady && (
                <ChooseImage label={t("office.chooseDarkLogo")} onChosen={(source) => setCropping({ source, dark: true })} />
              )}
            </>
          )}
        </div>
      )}

      {cropping && (
        <ImageCropDialog
          source={cropping.source}
          kind="logo"
          dark={cropping.dark}
          name={cropping.dark ? "logo-escuro.png" : "logo.png"}
          onCancel={stopCropping}
          onCropped={(file) => {
            const dark = cropping.dark;
            stopCropping();
            const done = { onError: (error: unknown) => toastError(error) };
            if (dark) darkLogo.mutate(file, { ...done, onSuccess: () => toast(t("office.darkLogoSaved")) });
            else logo.mutate(file, { ...done, onSuccess: () => toast(t("office.logoSaved")) });
          }}
        />
      )}
    </>
  );
}

/** "Escolher imagem": the file, as a local address for the crop dialog. */
function ChooseImage({ label, onChosen }: { label: string; onChosen: (source: string) => void }) {
  return (
    <FileTrigger
      acceptedFileTypes={["image/png", "image/jpeg", "image/webp", "image/svg+xml"]}
      onSelect={(files) => {
        const file = files?.[0];
        if (file) onChosen(URL.createObjectURL(file));
      }}
    >
      <Button>{label}</Button>
    </FileTrigger>
  );
}

/** The logo can't go up without the office's storage: why, and the way there
 *  (connect, or reconnect; a folder the portal can't read is fixed in settings). */
function NeedsDrive() {
  const { t } = useTranslation();
  const drive = useDrive();
  const connect = useConnectDrive();
  const status = drive.data;
  const expired = status?.kind === "google" && status.writer_status === "expired";
  const connected = status?.kind === "google" && status.writer_status === "connected";
  return (
    <div className={styles.warning} role="status">
      <p>{t(connected ? "office.logoDriveUnreadable" : "office.logoNeedsDrive")}</p>
      {connected ? (
        <Link className={styles.noticeAction} to="/configuracoes/drive">
          {t("settings.drive")}
        </Link>
      ) : (
        <Button variant="primary" onPress={() => connect.mutate(false)} isDisabled={connect.isPending}>
          {t(expired ? "drive.reconnect" : "drive.connect")}
        </Button>
      )}
      <ErrorNotice error={connect.error} />
    </div>
  );
}
