// The proposal generator (A40): /painel/projetos/{id}/proposta. The form on the
// left, the proposal as the client will see it on the right (on phones, under
// the form). Saving makes the next version, shown on the project page at once;
// nothing is emailed: staff send the page's link when they choose.
import { useEffect, useMemo, useRef, useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import type { Schemas } from "../api/client";
import { LIMITS } from "../api/limits";
import { ActionMenu } from "../ui/ActionMenu";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextAreaField, TextField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import { ProposalLetter } from "./ProposalLetter";
import {
  formatAmount,
  instalments,
  parseAmount,
  previewPage,
  previewPdf,
  useAcceptProposal,
  useGenerator,
  useSaveDefaults,
  useSavePresets,
  useSaveProposal,
  type Generator,
  type Preset,
  type ProposalContent,
  type ProposalView,
} from "./proposals";
import styles from "./proposals.module.css";
import { useOffice } from "../office/office";

type Draft = {
  client_name: string;
  city: string;
  date: string; // YYYY-MM-DD
  intro: string;
  services: Preset[];
  fee: string; // as typed: "29.000,00"
  payments: { amount: string; when: string }[];
  not_included: string; // one per line
  notes: string;
  signatory: string;
  address: string;
  phone: string;
  email: string;
};

function draftFrom(start: Generator["start"], locale: string): Draft {
  return {
    client_name: start.client_name,
    city: start.city ?? "",
    date: start.date,
    intro: start.intro ?? "",
    services: (start.services ?? []).map((s) => ({ title: s.title, description: s.description ?? "" })),
    fee: start.fee ? formatAmount(start.fee, locale) : "",
    payments: (start.payments ?? []).map((p) => ({ amount: formatAmount(p.amount, locale), when: p.when })),
    not_included: (start.not_included ?? []).join("\n"),
    notes: start.notes ?? "",
    signatory: start.signatory ?? "",
    address: start.address ?? "",
    phone: start.phone ?? "",
    email: start.email ?? "",
  };
}

type Checked = { content: ProposalContent } | { problem: string };

/** The draft as the API takes it, or what to fix first (in the user's words). */
function check(draft: Draft, locale: string, t: (key: string) => string): Checked {
  const fee = parseAmount(draft.fee, locale);
  if (!draft.client_name.trim()) return { problem: t("proposal.generator.needsClient") };
  if (draft.services.length === 0) return { problem: t("proposal.generator.needsService") };
  if (draft.services.some((s) => !s.title.trim())) return { problem: t("proposal.generator.needsServiceTitle") };
  if (!fee) return { problem: t("proposal.generator.needsFee") };
  const payments = draft.payments
    .filter((p) => p.amount.trim() || p.when.trim())
    .map((p) => ({ amount: parseAmount(p.amount, locale), when: p.when }));
  if (payments.some((p) => !p.amount)) return { problem: t("proposal.generator.badPayment") };
  return {
    content: {
      ...draft,
      fee,
      payments: payments as { amount: number; when: string }[],
      not_included: draft.not_included.split("\n").map((line) => line.trim()).filter(Boolean),
    },
  };
}

/** What the live preview sends: like `check`, but anything unfinished is left out. */
function previewBody(draft: Draft, locale: string): Schemas["ProposalStart"] {
  return {
    ...draft,
    client_name: draft.client_name.trim() || "—",
    services: draft.services.filter((s) => s.title.trim()),
    fee: parseAmount(draft.fee, locale) || null,
    payments: draft.payments.flatMap((p) => {
      const amount = parseAmount(p.amount, locale);
      return amount ? [{ amount, when: p.when }] : [];
    }),
    not_included: draft.not_included.split("\n").map((line) => line.trim()).filter(Boolean),
  };
}

const same = (a: Preset, b: Preset) => a.title.trim() === b.title.trim() && a.description.trim() === b.description.trim();
const sameTitle = (a: Preset, b: Preset) => a.title.trim().toLocaleLowerCase() === b.title.trim().toLocaleLowerCase();

export function ProposalPage() {
  const { projectId = "" } = useParams();
  const { t } = useTranslation();
  const generator = useGenerator(projectId);
  if (generator.error) return <ErrorNotice error={generator.error} />;
  if (!generator.data) return <p className={styles.lead}>{t("app.loading")}</p>;
  // A fresh form whenever another version is saved elsewhere and reloaded.
  return <Generator key={generator.data.versions[0]?.version ?? 0} data={generator.data} />;
}

function Generator({ data }: { data: Generator }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const office = useOffice();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(data.start, locale));
  const [dirty, setDirty] = useState(false);
  const change = (next: Partial<Draft>) => {
    setDraft((was) => ({ ...was, ...next }));
    setDirty(true);
  };
  const save = useSaveProposal(data.project_id);
  const accept = useAcceptProposal(data.project_id);
  const savePresets = useSavePresets(data.project_id);
  const saveDefaults = useSaveDefaults(data.project_id);
  const [problem, setProblem] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [instalmentCount, setInstalmentCount] = useState("4");

  // Leaving with unsaved changes asks first (the browser's own question).
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // The live preview, a moment after typing stops; the last good one stays meanwhile.
  const [preview, setPreview] = useState<ProposalView | null>(null);
  const body = useMemo(() => JSON.stringify(previewBody(draft, locale)), [draft, locale]);
  useEffect(() => {
    let current = true;
    const timer = window.setTimeout(() => {
      previewPage(data.project_id, JSON.parse(body)).then(
        (shown) => current && setPreview(shown),
        () => undefined, // something unfinished: keep the last preview
      );
    }, 400);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [body, data.project_id]);

  const services = draft.services;
  const setService = (index: number, next: Partial<Preset>) =>
    change({ services: services.map((s, i) => (i === index ? { ...s, ...next } : s)) });
  const move = (index: number, by: number) => {
    const list = [...services];
    const [moved] = list.splice(index, 1);
    list.splice(index + by, 0, moved!);
    change({ services: list });
  };
  const notListed = data.presets.filter((preset) => !services.some((s) => sameTitle(s, preset)));
  const saveAsPreset = (service: Preset) => {
    const list = data.presets.some((p) => sameTitle(p, service))
      ? data.presets.map((p) => (sameTitle(p, service) ? service : p))
      : [...data.presets, service];
    savePresets.mutate(list, {
      onSuccess: () => toast(t("proposal.generator.presetSaved", { title: service.title })),
      onError: (failure) => toastError(failure),
    });
  };

  const fee = parseAmount(draft.fee, locale);
  const paid = draft.payments.reduce((sum, p) => sum + (parseAmount(p.amount, locale) ?? 0), 0);
  const spread = () => {
    const count = Math.min(Math.max(Number(instalmentCount) || 1, 1), LIMITS.proposalPayments);
    if (!fee) return setProblem(t("proposal.generator.needsFee"));
    setProblem(null);
    change({
      payments: instalments(fee, count).map((amount, i) => ({
        amount: formatAmount(amount, locale),
        when: i === 0 ? t("proposal.generator.onAcceptance") : t("proposal.generator.daysAfter", { days: i * 30 }),
      })),
    });
  };

  const pdfWindow = useRef<Window | null>(null);
  const openPdf = () => {
    const checked = check(draft, locale, t);
    if ("problem" in checked) return setProblem(checked.problem);
    setProblem(null);
    // Opened at once, so the browser lets it through; the PDF follows.
    pdfWindow.current = window.open("", "_blank");
    previewPdf(data.project_id, checked.content).then(
      (pdf) => {
        const url = URL.createObjectURL(pdf);
        if (pdfWindow.current) pdfWindow.current.location.href = url;
        else window.location.href = url;
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      (failure) => {
        pdfWindow.current?.close();
        toastError(failure);
      },
    );
  };

  const submit = () => {
    const checked = check(draft, locale, t);
    if ("problem" in checked) return setProblem(checked.problem);
    setProblem(null);
    save.mutate(checked.content, {
      onSuccess: (saved) => {
        setDirty(false);
        toast(t("proposal.generator.saved", { version: saved.version }));
      },
    });
  };

  const isProposal = data.status === "proposal";
  const archived = data.status === "archived";
  const pageUrl = `/${data.slug}`;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <nav className={styles.crumbs} aria-label={t("proposal.generator.where")}>
          <Link to="/">{t("nav.projects")}</Link>
          <span aria-hidden="true">/</span>
          <a href={pageUrl}>{data.project_name}</a>
        </nav>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{t("proposal.generator.title")}</h1>
        </div>
        <p className={styles.lead}>
          {isProposal ? t("proposal.generator.leadProposal") : t("proposal.generator.lead")}
        </p>
        <div className={styles.headActions}>
          <a className={styles.linkButton} href={pageUrl}>
            {t("proposal.generator.openPage")}
          </a>
          {isProposal && (
            <Button size="small" onPress={() => setAccepting(true)}>
              {t("proposal.accept.action")}
            </Button>
          )}
        </div>
        {archived && <p className={styles.note}>{t("proposal.generator.archived")}</p>}
      </header>

      <div className={styles.layout}>
        <Form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <section className={styles.section} aria-labelledby="p-to">
            <h2 id="p-to">{t("proposal.generator.to")}</h2>
            <TextField
              label={t("proposal.generator.client")}
              description={t("proposal.generator.clientHint")}
              value={draft.client_name}
              onChange={(client_name) => change({ client_name })}
              maxLength={LIMITS.proposalClient}
              isRequired
            />
            <div className={styles.pair}>
              <TextField
                label={t("proposal.generator.city")}
                value={draft.city}
                onChange={(city) => change({ city })}
                maxLength={LIMITS.proposalCity}
              />
              <TextField
                label={t("proposal.generator.date")}
                type="date"
                value={draft.date}
                onChange={(date) => date && change({ date })}
                isRequired
              />
            </div>
            <DefaultText
              label={t("proposal.generator.intro")}
              value={draft.intro}
              onChange={(intro) => change({ intro })}
              maxLength={LIMITS.proposalIntro}
              saved={data.default_intro}
              busy={saveDefaults.isPending}
              onSaveDefault={() =>
                saveDefaults.mutate(
                  { intro: draft.intro },
                  { onSuccess: () => toast(t("proposal.generator.defaultSaved")), onError: (e) => toastError(e) },
                )
              }
            />
          </section>

          <section className={styles.section} aria-labelledby="p-services">
            <h2 id="p-services">{t("proposal.generator.services")}</h2>
            <p className={styles.hint}>{t("proposal.generator.servicesHint")}</p>
            <ol className={styles.services}>
              {services.map((service, i) => {
                const preset = data.presets.find((p) => sameTitle(p, service));
                const isDefault = preset !== undefined && same(preset, service);
                return (
                  <li key={i} className={styles.service}>
                    <div className={styles.serviceHead}>
                      <span className={styles.number}>{i + 1}.</span>
                      <div className={styles.serviceTools}>
                        <Button size="small" variant="ghost" isDisabled={i === 0} onPress={() => move(i, -1)} aria-label={t("proposal.generator.moveUp", { title: service.title })}>
                          ↑
                        </Button>
                        <Button size="small" variant="ghost" isDisabled={i === services.length - 1} onPress={() => move(i, 1)} aria-label={t("proposal.generator.moveDown", { title: service.title })}>
                          ↓
                        </Button>
                        <Button size="small" variant="ghost" onPress={() => change({ services: services.filter((_, j) => j !== i) })}>
                          {t("proposal.generator.remove")}
                        </Button>
                      </div>
                    </div>
                    <TextField
                      label={t("proposal.generator.serviceTitle")}
                      value={service.title}
                      onChange={(title) => setService(i, { title })}
                      maxLength={LIMITS.serviceTitle}
                      isRequired
                    />
                    <TextAreaField
                      label={t("proposal.generator.serviceDescription")}
                      value={service.description}
                      onChange={(description) => setService(i, { description })}
                      maxLength={LIMITS.serviceDescription}
                    />
                    {!isDefault && service.title.trim() && (
                      <Button size="small" className={styles.saveDefault} isDisabled={savePresets.isPending} onPress={() => saveAsPreset(service)}>
                        {preset ? t("proposal.generator.updatePreset") : t("proposal.generator.addPreset")}
                      </Button>
                    )}
                  </li>
                );
              })}
            </ol>
            {services.length < LIMITS.proposalServices && (
              <ActionMenu
                label={t("proposal.generator.addService")}
                className={styles.addButton}
                placement="bottom start"
                items={[
                  ...notListed.map((preset, i) => ({ id: `preset-${i}`, label: preset.title })),
                  { id: "blank", label: t("proposal.generator.blankService") },
                ]}
                onAction={(id) => {
                  const preset = id.startsWith("preset-") ? notListed[Number(id.slice(7))] : undefined;
                  change({ services: [...services, preset ? { ...preset } : { title: "", description: "" }] });
                }}
              >
                + {t("proposal.generator.addService")}
              </ActionMenu>
            )}
          </section>

          <section className={styles.section} aria-labelledby="p-fees">
            <h2 id="p-fees">{t("proposal.generator.fees")}</h2>
            <TextField
              label={t("proposal.generator.fee")}
              description={preview?.fee_in_words || t("proposal.generator.feeHint")}
              value={draft.fee}
              onChange={(value) => change({ fee: value })}
              onBlur={() => fee && change({ fee: formatAmount(fee, locale) })}
              inputMode="decimal"
              placeholder="29.000,00"
            />
            <h3 className={styles.subhead}>{t("proposal.generator.payments")}</h3>
            <div className={styles.spread}>
              <span>{t("proposal.generator.spreadInto")}</span>
              <input
                className={styles.count}
                type="number"
                min={1}
                max={LIMITS.proposalPayments}
                value={instalmentCount}
                onChange={(event) => setInstalmentCount(event.target.value)}
                aria-label={t("proposal.generator.instalmentCount")}
              />
              <span>{t("proposal.generator.instalments")}</span>
              <Button size="small" onPress={spread}>
                {t("proposal.generator.spread")}
              </Button>
            </div>
            <ul className={styles.payments}>
              {draft.payments.map((payment, i) => (
                <li key={i} className={styles.payment}>
                  <TextField
                    label={t("proposal.generator.amount")}
                    value={payment.amount}
                    inputMode="decimal"
                    onChange={(amount) =>
                      change({ payments: draft.payments.map((p, j) => (j === i ? { ...p, amount } : p)) })
                    }
                  />
                  <TextField
                    label={t("proposal.generator.when")}
                    value={payment.when}
                    maxLength={LIMITS.proposalLine}
                    onChange={(when) => change({ payments: draft.payments.map((p, j) => (j === i ? { ...p, when } : p)) })}
                  />
                  <Button
                    size="small"
                    variant="ghost"
                    className={styles.removePayment}
                    onPress={() => change({ payments: draft.payments.filter((_, j) => j !== i) })}
                  >
                    {t("proposal.generator.remove")}
                  </Button>
                </li>
              ))}
            </ul>
            {draft.payments.length < LIMITS.proposalPayments && (
              <Button
                size="small"
                className={styles.addPayment}
                onPress={() => change({ payments: [...draft.payments, { amount: "", when: "" }] })}
              >
                + {t("proposal.generator.addPayment")}
              </Button>
            )}
            {fee !== null && draft.payments.length > 0 && paid !== fee && (
              <p className={styles.warning} role="note">
                {t("proposal.generator.paymentsDiffer", {
                  paid: formatAmount(paid, locale),
                  fee: formatAmount(fee, locale),
                })}
              </p>
            )}
          </section>

          <section className={styles.section} aria-labelledby="p-terms">
            <h2 id="p-terms">{t("proposal.generator.terms")}</h2>
            <TextAreaField
              label={t("proposal.generator.notIncluded")}
              description={t("proposal.generator.notIncludedHint")}
              value={draft.not_included}
              onChange={(not_included) => change({ not_included })}
            />
            <DefaultText
              label={t("proposal.generator.notes")}
              value={draft.notes}
              onChange={(notes) => change({ notes })}
              maxLength={LIMITS.proposalNotes}
              rows={6}
              saved={data.default_notes}
              busy={saveDefaults.isPending}
              onSaveDefault={() =>
                saveDefaults.mutate(
                  { notes: draft.notes },
                  { onSuccess: () => toast(t("proposal.generator.defaultSaved")), onError: (e) => toastError(e) },
                )
              }
            />
          </section>

          <section className={styles.section} aria-labelledby="p-office">
            <h2 id="p-office">{t("proposal.generator.office")}</h2>
            <p className={styles.hint}>{t("proposal.generator.officeHint")}</p>
            <TextField
              label={t("proposal.generator.signatory")}
              description={t("proposal.generator.signatoryHint")}
              value={draft.signatory}
              onChange={(signatory) => change({ signatory })}
              maxLength={LIMITS.proposalSignatory}
            />
            <TextField
              label={t("proposal.generator.address")}
              value={draft.address}
              onChange={(address) => change({ address })}
              maxLength={LIMITS.proposalAddress}
            />
            <div className={styles.pair}>
              <TextField
                label={t("proposal.generator.phone")}
                value={draft.phone}
                onChange={(phone) => change({ phone })}
                maxLength={LIMITS.proposalPhone}
                type="tel"
              />
              <TextField
                label={t("proposal.generator.email")}
                value={draft.email}
                onChange={(email) => change({ email })}
                maxLength={LIMITS.email}
                type="email"
              />
            </div>
          </section>

          <div className={styles.actions}>
            {problem && (
              <p role="alert" className={styles.problem}>
                {problem}
              </p>
            )}
            <ErrorNotice error={save.error} />
            <div className={styles.buttons}>
              <Button onPress={openPdf}>{t("proposal.generator.viewPdf")}</Button>
              <Button type="submit" variant="primary" isDisabled={save.isPending || archived}>
                {save.isPending ? t("proposal.generator.saving") : t("proposal.generator.save")}
              </Button>
            </div>
            <p className={styles.hint}>{t("proposal.generator.saveHint")}</p>
          </div>

          {data.versions.length > 0 && (
            <section className={styles.section} aria-labelledby="p-versions">
              <h2 id="p-versions">{t("proposal.generator.versions")}</h2>
              <ul className={styles.versions}>
                {data.versions.map((version) => (
                  <li key={version.version}>
                    <span>
                      {t("proposal.generator.version", {
                        version: version.version,
                        date: new Date(version.created_at).toLocaleDateString(locale),
                        name: version.created_by ?? "—",
                      })}
                      {version === data.versions[0] && ` · ${t("proposal.generator.latest")}`}
                    </span>
                    <a href={`/api/projects/${data.project_id}/proposals/${version.version}/pdf?download=true`}>
                      {t("proposal.generator.download")}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </Form>

        <aside className={styles.preview} aria-label={t("proposal.generator.preview")}>
          <p className={styles.previewLabel}>{t("proposal.generator.preview")}</p>
          {preview ? (
            <ProposalLetter
              proposal={preview}
              office={{ name: office.data?.name ?? "", logo_url: office.data?.logo_url }}
            />
          ) : (
            <p className={styles.hint}>{t("app.loading")}</p>
          )}
        </aside>
      </div>

      {accepting && (
        <ConfirmDialog
          title={t("proposal.accept.ask")}
          text={t("proposal.accept.means")}
          confirm={t("proposal.accept.confirm")}
          busy={accept.isPending}
          onCancel={() => setAccepting(false)}
          onConfirm={() =>
            accept.mutate(data.row_version, {
              onSuccess: () => {
                setAccepting(false);
                toast(t("proposal.accept.done"));
              },
              onError: (failure) => {
                setAccepting(false);
                toastError(failure);
              },
            })
          }
        />
      )}
    </div>
  );
}

/** A text new proposals start with: "Salvar como padrão" once it differs. */
function DefaultText({
  label,
  value,
  onChange,
  maxLength,
  rows = 3,
  saved,
  busy,
  onSaveDefault,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  maxLength: number;
  rows?: number;
  saved: string;
  busy: boolean;
  onSaveDefault: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.withDefault}>
      <TextAreaField label={label} value={value} onChange={onChange} maxLength={maxLength} rows={rows} />
      {value.trim() !== saved.trim() && (
        <Button size="small" className={styles.saveDefault} isDisabled={busy} onPress={onSaveDefault}>
          {t("proposal.generator.saveDefault")}
        </Button>
      )}
    </div>
  );
}
