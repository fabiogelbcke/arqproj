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
  const [hostname, setHostname] = useState("");
  const [edited, setEdited] = useState<string | null>(null);
  const slug = edited ?? slugFromHost(hostname);
  const create = useMutation({
    mutationFn: () => call(api.POST("/api/admin/offices", { body: { name, slug, hostname: hostOf(hostname) } })),
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
          <TextField label={t("admin.actions.hostname")} placeholder={t("admin.actions.hostnameExample")} value={hostname} onChange={setHostname} isRequired autoComplete="off" />
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
