import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { api, call, type Schemas } from "../api/client";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { LinkToCopy } from "../ui/LinkToCopy";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import { ToggleSwitch } from "../ui/ToggleSwitch";
import ui from "../ui/ui.module.css";
import styles from "./admin.module.css";

type Action = Schemas["TenantActionIn"]["action"];

/** What was typed as an address, as the server takes it: no https://, path or case. */
export function hostOf(value: string) {
  return value.trim().toLowerCase().replace(/^[a-z]+:\/\//, "").replace(/[/?#].*$/, "").replace(/\.$/, "");
}

/** The identifier an address suggests: its first part (alinea.myunio.app → alinea). */
export function slugFromHost(value: string) {
  return (hostOf(value).split(".")[0] ?? "").replace(/[^a-z0-9-]/g, "").replace(/^-+|-+$/g, "").slice(0, 63);
}

/** The office's part of its address, at most: the same as the signup page's
 *  (Fabio, 28 Oct 2026). Short enough to type and read in a link. */
const ADDRESS_MAX = 40;

/** Where a new office is served: `{office}.myunio.app` (A21), or `{office}.localhost`
 *  on a local run. */
export function officeDomain(host = window.location.hostname) {
  return host === "localhost" || host.endsWith(".localhost") ? ".localhost" : ".myunio.app";
}

/** The office's own part of an address, typed alone or pasted whole
 *  (https://Horizonte.myunio.app/ → horizonte). */
export function subdomainOf(value: string, domain: string) {
  const host = hostOf(value);
  return host.endsWith(domain) ? host.slice(0, -domain.length) : value;
}

/** The owner's one-time signup link, shown once, to copy. */
function OwnerLink({ url, onDone }: { url: string; onDone: () => void }) {
  const { t } = useTranslation();
  return (
    <div className={styles.dialogBody} role="status">
      <p>{t("admin.actions.ownerHelp")}</p>
      <LinkToCopy link={url} label={t("admin.actions.ownerLink")} />
      <div className={styles.dialogActions}>
        <Button variant="primary" onPress={onDone}>{t("admin.actions.close")}</Button>
      </div>
    </div>
  );
}

/** "Criar escritório", in a dialog like the painel's: the identifier follows the
 *  address until it is edited, since it can't change afterwards. */
export function CreateTenant() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return <>
    <Button variant="primary" onPress={() => setOpen(true)}>{t("admin.actions.create")}</Button>
    {open && <CreateTenantDialog onClose={() => setOpen(false)} />}
  </>;
}

function CreateTenantDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const [name, setName] = useState("");
  const domain = officeDomain();
  const [subdomain, setSubdomain] = useState("");
  const hostname = hostOf(subdomain) + domain;
  const [edited, setEdited] = useState<string | null>(null);
  const slug = edited ?? slugFromHost(hostname);
  const create = useMutation({
    mutationFn: () => call(api.POST("/api/admin/offices", { body: { name, slug, hostname } })),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["admin", "offices"] }),
  });
  // Open until the request answers: its owner link is shown only here (Codex, PR #149).
  const close = () => !create.isPending && onClose();
  return (
    <DialogFrame title={t("admin.actions.create")} onClose={close}>
      {create.data?.owner_url ? (
        <OwnerLink url={create.data.owner_url} onDone={onClose} />
      ) : (
        <Form className={styles.dialogBody} onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
          <TextField label={t("admin.actions.name")} value={name} onChange={setName} isRequired autoFocus autoComplete="off" />
          <TextField label={t("admin.actions.hostname")} description={t("admin.actions.hostnameHint")} placeholder={t("admin.actions.hostnameExample")} suffix={domain} maxLength={ADDRESS_MAX} value={subdomain} onChange={(value) => setSubdomain(subdomainOf(value, domain))} isRequired autoComplete="off" />
          <TextField label={t("admin.actions.slug")} description={t("admin.actions.slugHint")} value={slug} onChange={setEdited} isRequired autoComplete="off" />
          <ErrorNotice error={create.error} />
          <div className={styles.dialogActions}>
            <Button onPress={close} isDisabled={create.isPending}>{t("admin.actions.cancel")}</Button>
            <Button type="submit" variant="primary" isDisabled={create.isPending}>{t("admin.actions.createConfirm")}</Button>
          </div>
        </Form>
      )}
    </DialogFrame>
  );
}

/** "Link para criar escritório": a one-time link whose holder creates their
 *  own office (name and address) and then their owner account. Shown once. */
export function SignupLink() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return <>
    <Button onPress={() => setOpen(true)}>{t("admin.actions.signupLink")}</Button>
    {open && <SignupLinkDialog onClose={() => setOpen(false)} />}
  </>;
}

function SignupLinkDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const make = useMutation({ mutationFn: () => call(api.POST("/api/admin/signup-links")) });
  const close = () => !make.isPending && onClose();
  return (
    <DialogFrame title={t("admin.actions.signupLink")} onClose={close}>
      {make.data ? (
        <div className={styles.dialogBody} role="status">
          <p>{t("admin.actions.signupLinkHelp")}</p>
          <LinkToCopy link={make.data.url} label={t("admin.actions.signupLink")} />
          <div className={styles.dialogActions}>
            <Button variant="primary" onPress={onClose}>{t("admin.actions.close")}</Button>
          </div>
        </div>
      ) : (
        <Form className={styles.dialogBody} onSubmit={(event) => { event.preventDefault(); make.mutate(); }}>
          <p>{t("admin.actions.signupLinkExplain")}</p>
          <ErrorNotice error={make.error} />
          <div className={styles.dialogActions}>
            <Button onPress={close} isDisabled={make.isPending}>{t("admin.actions.cancel")}</Button>
            <Button type="submit" variant="primary" isDisabled={make.isPending}>{t("admin.actions.signupLinkMake")}</Button>
          </div>
        </Form>
      )}
    </DialogFrame>
  );
}

/** An office's actions, beside its name: each asks first, in a dialog. */
export function TenantActions({ office }: { office: Schemas["AdminOfficeOut"] }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Action | null>(null);
  const choices = office.status === "active" ? (["owner_link", "suspend"] as const) : (["restore", "delete"] as const);
  return <>
    {choices.map((choice) => (
      <Button key={choice} size="small" onPress={() => setSelected(choice)}>{t(`admin.actions.${choice}`)}</Button>
    ))}
    {selected && <ActionDialog key={selected} office={office} action={selected} onClose={() => setSelected(null)} />}
  </>;
}

function ActionDialog({ office, action, onClose }: { office: Schemas["AdminOfficeOut"]; action: Action; onClose: () => void }) {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [confirmation, setConfirmation] = useState("");
  const run = useMutation({
    mutationFn: () => call(api.POST("/api/admin/offices/{slug}/actions", { params: { path: { slug: office.slug } }, body: { action, confirmation } })),
    onSuccess: (out) => {
      void cache.invalidateQueries({ queryKey: ["admin"] });
      if (out.owner_url) return;
      toast(t("admin.actions.done"));
      onClose();
      if (action === "delete") void navigate("/");
    },
  });
  // As creating: closing mid-request would hide its result, or seem to cancel it.
  const close = () => !run.isPending && onClose();
  return (
    <DialogFrame title={t(`admin.actions.${action}`)} onClose={close}>
      {run.data?.owner_url ? (
        <OwnerLink url={run.data.owner_url} onDone={onClose} />
      ) : (
        <Form className={styles.dialogBody} onSubmit={(event) => { event.preventDefault(); run.mutate(); }}>
          <p>{t(`admin.actions.explain.${action}`, { name: office.name })}</p>
          {action === "delete" && <TextField label={t("admin.actions.confirmName")} value={confirmation} onChange={setConfirmation} isRequired autoComplete="off" />}
          <ErrorNotice error={run.error} />
          <div className={styles.dialogActions}>
            <Button onPress={close} isDisabled={run.isPending}>{t("admin.actions.cancel")}</Button>
            <Button type="submit" variant="primary" className={action === "delete" || action === "suspend" ? ui.dangerAction : undefined} isDisabled={run.isPending || (action === "delete" && confirmation !== office.name)}>
              {t("admin.actions.confirm")}
            </Button>
          </div>
        </Form>
      )}
    </DialogFrame>
  );
}

/** "Funções em teste" (A40): work merged but switched on only for some offices.
 *  One switch per feature; switching back undoes it, so it doesn't ask first. */
export function Features({ office }: { office: Schemas["AdminOfficeOut"] }) {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const run = useMutation({
    mutationFn: ({ feature, on }: { feature: Schemas["Feature"]; on: boolean }) =>
      call(api.POST("/api/admin/offices/{slug}/actions", { params: { path: { slug: office.slug } }, body: { action: on ? "feature_on" : "feature_off", feature, confirmation: "" } })),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["admin"] });
      toast(t("admin.actions.done"));
    },
  });
  return <>
    <ul className={styles.features}>
      {office.all_features.map((feature) => {
        const on = office.features.includes(feature);
        return (
          <li key={feature}>
            <div>
              <b>{t(`admin.feature.${feature}.name`)}</b>
              <span className={styles.muted}>{t(`admin.feature.${feature}.about`)}</span>
            </div>
            <ToggleSwitch
              label={t(`admin.feature.${feature}.name`)}
              isSelected={on}
              isDisabled={run.isPending}
              onChange={(next) => run.mutate({ feature, on: next })}
            >
              <span className={styles.muted}>{on ? t("admin.featureOn") : t("admin.featureOff")}</span>
            </ToggleSwitch>
          </li>
        );
      })}
    </ul>
    <ErrorNotice error={run.error} />
  </>;
}
