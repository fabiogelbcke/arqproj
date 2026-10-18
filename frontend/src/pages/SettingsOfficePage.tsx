import { useState } from "react";
import { FileTrigger, Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { useDrive } from "../drive/drive";
import { useOffice, useSaveOffice, useUploadLogo } from "../office/office";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
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
  const office = useOffice();
  const drive = useDrive();
  const save = useSaveOffice();
  const logo = useUploadLogo();
  const [draft, setDraft] = useState<{ name: string; contact_email: string } | null>(null);

  if (office.error) return <ErrorNotice error={office.error} />;
  if (!office.data) return <p className={styles.lead}>{t("app.loading")}</p>;
  const details = office.data;
  const values = draft ?? { name: details.name, contact_email: details.contact_email ?? "" };
  const manage = details.can_manage;
  // The logo lives in the office's storage: Google Drive connected, or local folders.
  // On Drive, both paths must work: the office's grant writes it, the reader shows it.
  const storageReady =
    drive.data?.kind === "folder" ||
    (drive.data?.kind === "google" &&
      drive.data.writer_status === "connected" &&
      drive.data.reader_status === "ok");

  return (
    <section className={styles.panel} aria-labelledby="office-title">
      <h2 id="office-title" className="sr-only">
        {t("settings.office")}
      </h2>
      {!manage && <p className={styles.small}>{t("office.ownerOnly")}</p>}
      <Form
        onSubmit={(event) => {
          event.preventDefault();
          const submitted = values;
          // Keep anything typed while the save was on its way.
          save.mutate(submitted, {
            onSuccess: () => setDraft((current) => (current === submitted ? null : current)),
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
          maxLength={28} // for now (Fabio, 18 Oct 2026); the API checks the same
          isReadOnly={!manage}
        />
        <TextField
          label={t("office.email")}
          description={t("office.emailHint")}
          type="email"
          value={values.contact_email}
          onChange={(contact_email) => setDraft({ ...values, contact_email })}
          isReadOnly={!manage}
        />
        <ErrorNotice error={save.error} />
        {save.isSuccess && !draft && <p role="status">{t("office.saved")}</p>}
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
        {details.logo_url ? (
          <img className={styles.logo} src={details.logo_url} alt={t("office.logoAlt", { name: details.name })} />
        ) : (
          // An empty slot with the office's initials until a logo is uploaded.
          <div className={styles.logoEmpty} role="img" aria-label={t("office.logoNone")}>
            <span aria-hidden="true">{initials(details.name)}</span>
            <small>{t("office.logoNone")}</small>
          </div>
        )}
        <p className={styles.small}>{t("office.logoHint")}</p>
        {manage &&
          (storageReady ? (
            <FileTrigger
              acceptedFileTypes={["image/png", "image/jpeg", "image/webp", "image/svg+xml"]}
              onSelect={(files) => {
                const file = files?.[0];
                if (file) logo.mutate(file);
              }}
            >
              <Button isDisabled={logo.isPending}>{t("office.chooseLogo")}</Button>
            </FileTrigger>
          ) : (
            <p className={styles.small}>{t("office.logoNeedsDrive")}</p>
          ))}
        <ErrorNotice error={logo.error} />
        {logo.isSuccess && <p role="status">{t("office.logoSaved")}</p>}
      </div>
    </section>
  );
}
