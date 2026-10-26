import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { api, call, type Schemas } from "../api/client";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";
import { ErrorNotice } from "../ui/ErrorNotice";
import styles from "./admin.module.css";

function OwnerLink({ url }: { url?: string | null }) {
  const { t } = useTranslation();
  if (!url) return null;
  return <div><p>{t("admin.actions.ownerHelp")}</p><TextField label={t("admin.actions.ownerLink")} value={url} isReadOnly /></div>;
}

export function CreateTenant() {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [hostname, setHostname] = useState("");
  const create = useMutation({
    mutationFn: () => call(api.POST("/api/admin/offices", { body: { name, slug, hostname } })),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["admin", "offices"] }),
  });
  return <section className={styles.panel}>
    <Button onPress={() => { if (!open) { create.reset(); setName(""); setSlug(""); setHostname(""); } setOpen(!open); }}>{t("admin.actions.create")}</Button>
    {open && <Form className={styles.devForm} onSubmit={event => { event.preventDefault(); create.mutate(); }}>
      <TextField label={t("admin.actions.name")} value={name} onChange={setName} isRequired />
      <TextField label={t("admin.actions.slug")} value={slug} onChange={setSlug} isRequired />
      <TextField label={t("admin.actions.hostname")} value={hostname} onChange={setHostname} isRequired />
      <Button type="submit" isDisabled={create.isPending || create.isSuccess}>{t("admin.actions.createConfirm")}</Button>
      <ErrorNotice error={create.error} />
      <OwnerLink url={create.data?.owner_url} />
    </Form>}
  </section>;
}

export function TenantActions({ office }: { office: Schemas["AdminOfficeOut"] }) {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Schemas["TenantActionIn"]["action"] | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const action = useMutation({
    mutationFn: (choice: Schemas["TenantActionIn"]["action"]) => call(api.POST("/api/admin/offices/{slug}/actions", { params: { path: { slug: office.slug } }, body: { action: choice, confirmation } })),
    onSuccess: (_data, choice) => {
      setSelected(null);
      setConfirmation("");
      void cache.invalidateQueries({ queryKey: ["admin"] });
      if (choice === "delete") void navigate("/");
    },
  });
  return <section className={styles.panel}>
    <h2>{t("admin.actions.title")}</h2>
    <div className={styles.head}>
      {(office.status === "active" ? ["owner_link", "suspend"] as const : ["restore", "delete"] as const).map(choice => <Button key={choice} isDisabled={action.isPending} onPress={() => { action.reset(); setSelected(choice); }}>{t(`admin.actions.${choice}`)}</Button>)}
    </div>
    {selected && <Form className={styles.devForm} onSubmit={event => { event.preventDefault(); action.mutate(selected); }}>
      <p>{t(`admin.actions.explain.${selected}`, { name: office.name })}</p>
      {selected === "delete" && <TextField label={t("admin.actions.confirmName")} value={confirmation} onChange={setConfirmation} isRequired />}
      <div className={styles.head}>
        <Button type="submit" isDisabled={action.isPending || (selected === "delete" && confirmation !== office.name)}>{t("admin.actions.confirm")}</Button>
        <Button isDisabled={action.isPending} onPress={() => setSelected(null)}>{t("admin.actions.cancel")}</Button>
      </div>
    </Form>}
    <ErrorNotice error={action.error} />
    <OwnerLink url={action.data?.owner_url} />
    {action.isSuccess && !action.data.owner_url && <p role="status">{t("admin.actions.done")}</p>}
  </section>;
}
