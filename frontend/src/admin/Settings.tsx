// "Configurações" (A44): what is set for the whole site, beside "Escritórios".
// A side list of sections (Tipos de projeto, Etapas for now); each list in its
// order, moved up or down, with what's hidden marked and a form to add one.
import { useState, type ReactNode } from "react";
import { Dialog, Form, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet } from "react-router";

import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { Panel } from "../ui/Panel";
import { TextAreaField, TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import styles from "./admin.module.css";
import { moved, useAddStage, useAddType, useCatalog, useReorder, type Catalog, type Texts } from "./siteSettings";

export function SettingsLayout() {
  const { t } = useTranslation();
  const catalog = useCatalog();
  return (
    <>
      <header className={styles.pageHead}>
        <div className={styles.titleBlock}>
          <h1>{t("admin.settings.title")}</h1>
          <p className={styles.mutedText}>{t("admin.settings.intro")}</p>
        </div>
      </header>
      <div className={styles.settings}>
        <nav className={styles.sideNav} aria-label={t("admin.settings.sections")}>
          <NavLink to="tipos">{t("admin.settings.types")}</NavLink>
          <NavLink to="etapas">{t("admin.settings.stages")}</NavLink>
        </nav>
        <div className={styles.stack}>
          <p className={styles.everywhere} role="note">
            <span aria-hidden="true">⚠</span> {t("admin.settings.everywhere")}
          </p>
          {catalog.data && !catalog.data.can_change && <p className={styles.mutedText}>{t("admin.settings.readOnly")}</p>}
          {catalog.isPending && <p className={styles.muted}>{t("app.loading")}</p>}
          <ErrorNotice error={catalog.error} />
          {catalog.data && <Outlet context={catalog.data} />}
        </div>
      </div>
    </>
  );
}

/** A name or description in both languages, side by side (English may be left blank). */
export function TextsFields({
  label,
  value,
  onChange,
  maxLength,
  multiline = false,
  isRequired = true,
  isDisabled,
  description,
}: {
  label: string;
  value: Texts;
  onChange: (value: Texts) => void;
  maxLength: number;
  multiline?: boolean;
  isRequired?: boolean;
  isDisabled?: boolean;
  description?: string;
}) {
  const { t } = useTranslation();
  const Field = multiline ? TextAreaField : TextField;
  return (
    <fieldset className={styles.texts} disabled={isDisabled}>
      <legend>{label}</legend>
      {description && <p className={styles.muted}>{description}</p>}
      <div className={styles.textsPair}>
        <Field
          label={t("admin.settings.pt")}
          value={value.pt}
          onChange={(pt) => onChange({ ...value, pt })}
          maxLength={maxLength}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
        <Field
          label={t("admin.settings.en")}
          description={t("admin.settings.enHint")}
          value={value.en}
          onChange={(en) => onChange({ ...value, en })}
          maxLength={maxLength}
          isDisabled={isDisabled}
        />
      </div>
    </fieldset>
  );
}

/** Before saving a change that reaches existing projects: in red, what changes
 *  and in how many projects, and a deliberate "Alterar mesmo assim" (Fabio). */
export function ChangeWarning({
  changes,
  busy,
  onConfirm,
  onCancel,
}: {
  changes: string[];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ModalOverlay className={styles.warningOverlay} isOpen onOpenChange={(open) => !open && onCancel()}>
      <Modal className={styles.warningModal}>
        <Dialog role="alertdialog" className={styles.warning}>
          <div className={styles.warningSign} aria-hidden="true">
            ⚠
          </div>
          <Heading slot="title" className={styles.warningTitle}>
            {t("admin.settings.warning.title")}
          </Heading>
          <p>{t("admin.settings.warning.lead")}</p>
          <ul className={styles.warningList}>
            {changes.map((change) => (
              <li key={change}>
                <span aria-hidden="true">⚠ </span>
                {change}
              </li>
            ))}
          </ul>
          <p className={styles.warningNote}>{t("admin.settings.warning.note")}</p>
          <div className={styles.dialogActions}>
            <Button onPress={onCancel} autoFocus>
              {t("admin.settings.warning.cancel")}
            </Button>
            <Button variant="danger" onPress={onConfirm} isDisabled={busy}>
              {t("admin.settings.warning.confirm")}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}

/** One row of a list: its place (↑ ↓), its name and facts, "Editar". */
function Row({
  name,
  hidden,
  facts,
  to,
  first,
  last,
  canMove,
  onMove,
}: {
  name: string;
  hidden: boolean;
  facts: ReactNode;
  to: string;
  first: boolean;
  last: boolean;
  canMove: boolean;
  onMove: (by: -1 | 1) => void;
}) {
  const { t } = useTranslation();
  return (
    <li className={styles.settingRow} data-hidden={hidden || undefined}>
      <div className={styles.moveButtons}>
        <Button size="small" variant="ghost" aria-label={t("admin.settings.moveUp", { name })} isDisabled={!canMove || first} onPress={() => onMove(-1)}>
          ↑
        </Button>
        <Button size="small" variant="ghost" aria-label={t("admin.settings.moveDown", { name })} isDisabled={!canMove || last} onPress={() => onMove(1)}>
          ↓
        </Button>
      </div>
      <div className={styles.settingName}>
        <span>
          {name}
          {hidden && <span className={styles.state}>{t("admin.settings.hidden")}</span>}
        </span>
        <span className={styles.muted}>{facts}</span>
      </div>
      <Link to={to} className={styles.headLink} aria-label={`${t("admin.settings.edit")} ${name}`}>
        {t("admin.settings.edit")}
      </Link>
    </li>
  );
}

/** "Novo tipo" / "Nova etapa": the name (and a stage's description), then its page. */
function AddForm({
  title,
  hint,
  children,
  ready,
  busy,
  error,
  onAdd,
}: {
  title: string;
  hint: string;
  children: ReactNode;
  ready: boolean;
  busy: boolean;
  error: unknown;
  onAdd: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Panel aria-label={title}>
      <Form
        className={styles.stack}
        onSubmit={(event) => {
          event.preventDefault();
          onAdd();
        }}
      >
        <h2>{title}</h2>
        <p className={styles.muted}>{hint}</p>
        {children}
        <ErrorNotice error={error} />
        <div>
          <Button type="submit" isDisabled={!ready || busy}>
            {t("admin.settings.add")}
          </Button>
        </div>
      </Form>
    </Panel>
  );
}

const EMPTY: Texts = { pt: "", en: "" };

export function TypesList({ catalog }: { catalog: Catalog }) {
  const { t } = useTranslation();
  const reorder = useReorder();
  const add = useAddType();
  const [labels, setLabels] = useState<Texts>(EMPTY);
  const keys = catalog.types.map((kind) => kind.key);
  return (
    <>
      <Panel aria-labelledby="types-title">
        <div className={styles.stack}>
          <h2 id="types-title">{t("admin.settings.types")}</h2>
          <p className={styles.muted}>{t("admin.settings.typesIntro")}</p>
          <ErrorNotice error={reorder.error} />
          <ol className={styles.settingList}>
            {catalog.types.map((kind, i) => (
              <Row
                key={kind.key}
                name={kind.labels.pt}
                hidden={kind.hidden}
                to={kind.key}
                first={i === 0}
                last={i === catalog.types.length - 1}
                canMove={catalog.can_change && !reorder.isPending}
                onMove={(by) => reorder.mutate({ kind: "types", keys: moved(keys, kind.key, by) })}
                facts={[
                  kind.lists_every_stage
                    ? t("admin.settings.everyStage")
                    : t("admin.settings.stagesListed", { count: kind.stages.length }),
                  t("admin.settings.projects", { count: kind.projects }),
                ].join(" · ")}
              />
            ))}
          </ol>
        </div>
      </Panel>
      {catalog.can_change && (
        <AddForm
          title={t("admin.settings.newType")}
          hint={t("admin.settings.newTypeHint")}
          ready={!!labels.pt.trim()}
          busy={add.isPending}
          error={add.error}
          onAdd={() =>
            add.mutate(
              { labels },
              {
                onSuccess: () => {
                  toast(t("admin.settings.typeAdded", { name: labels.pt.trim() }));
                  setLabels(EMPTY);
                },
              },
            )
          }
        >
          <TextsFields label={t("admin.settings.typeName")} value={labels} onChange={setLabels} maxLength={catalog.limits.typeLabel!} />
        </AddForm>
      )}
    </>
  );
}

export function StagesList({ catalog }: { catalog: Catalog }) {
  const { t } = useTranslation();
  const reorder = useReorder();
  const add = useAddStage();
  const [titles, setTitles] = useState<Texts>(EMPTY);
  const [about, setAbout] = useState<Texts>(EMPTY);
  const keys = catalog.stages.map((stage) => stage.key);
  return (
    <>
      <Panel aria-labelledby="stages-title">
        <div className={styles.stack}>
          <h2 id="stages-title">{t("admin.settings.stages")}</h2>
          <p className={styles.muted}>{t("admin.settings.stagesIntro")}</p>
          <ErrorNotice error={reorder.error} />
          <ol className={styles.settingList}>
            {catalog.stages.map((stage, i) => (
              <Row
                key={stage.key}
                name={stage.titles.pt}
                hidden={stage.hidden}
                to={stage.key}
                first={i === 0}
                last={i === catalog.stages.length - 1}
                canMove={catalog.can_change && !reorder.isPending}
                onMove={(by) => reorder.mutate({ kind: "stages", keys: moved(keys, stage.key, by) })}
                facts={t("admin.settings.projects", { count: stage.projects })}
              />
            ))}
          </ol>
        </div>
      </Panel>
      {catalog.can_change && (
        <AddForm
          title={t("admin.settings.newStage")}
          hint={t("admin.settings.newStageHint")}
          ready={!!titles.pt.trim() && !!about.pt.trim()}
          busy={add.isPending}
          error={add.error}
          onAdd={() =>
            add.mutate(
              { titles, about },
              {
                onSuccess: () => {
                  toast(t("admin.settings.stageAdded", { name: titles.pt.trim() }));
                  setTitles(EMPTY);
                  setAbout(EMPTY);
                },
              },
            )
          }
        >
          <TextsFields label={t("admin.settings.stageName")} value={titles} onChange={setTitles} maxLength={catalog.limits.stageTitle!} />
          <TextsFields label={t("admin.settings.stageAbout")} value={about} onChange={setAbout} maxLength={catalog.limits.stageAbout!} multiline />
        </AddForm>
      )}
    </>
  );
}
