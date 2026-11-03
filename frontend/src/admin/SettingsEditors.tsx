// One type's or one stage's page in "Configurações" (A44). Saving a change that
// reaches existing projects (a name, a description they show) first shows the red
// warning with how many projects it changes; hiding or listing reaches none.
import { useState } from "react";
import { Checkbox, Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, useOutletContext, useParams } from "react-router";

import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { Panel } from "../ui/Panel";
import { toast } from "../ui/Toast";
import { ToggleSwitch } from "../ui/ToggleSwitch";
import styles from "./admin.module.css";
import { ChangeWarning, StagesList, TextsFields, TypesList } from "./Settings";
import { sameTexts, useChangeStage, useChangeType, type Catalog, type SiteStage, type SiteType, type Texts } from "./siteSettings";

export function TypesPage() {
  return <TypesList catalog={useOutletContext<Catalog>()} />;
}

export function StagesPage() {
  return <StagesList catalog={useOutletContext<Catalog>()} />;
}

function NotFound({ list }: { list: string }) {
  const { t } = useTranslation();
  return (
    <p className={styles.mutedText}>
      {t("admin.settings.notFound")} <Link to=".." relative="path">{list}</Link>
    </p>
  );
}

/** "Salvar alterações", asking first with the warning when `changes` reach projects. */
function useGuardedSave(save: () => void) {
  const [warning, setWarning] = useState<string[] | null>(null);
  return {
    warning,
    ask: (changes: string[]) => (changes.length ? setWarning(changes) : save()),
    confirm: () => {
      setWarning(null);
      save();
    },
    cancel: () => setWarning(null),
  };
}

/** English blank again when it is the Portuguese (as a blank one is stored), so
 *  a later Portuguese fix reaches it. */
const editable = (texts: Texts): Texts => (texts.en.trim() === texts.pt.trim() ? { ...texts, en: "" } : texts);

// `writing`: its own-words fields shown (they are when it has some).
type Row = { key: string; listed: boolean; usual: boolean; about: Texts; writing: boolean };

export function TypePage() {
  const { t } = useTranslation();
  const catalog = useOutletContext<Catalog>();
  const { key = "" } = useParams();
  const kind = catalog.types.find((found) => found.key === key);
  // A fresh form whenever the saved type changes (its own save included).
  return kind ? <TypeForm key={JSON.stringify(kind)} catalog={catalog} kind={kind} /> : <NotFound list={t("admin.settings.types")} />;
}

function TypeForm({ catalog, kind }: { catalog: Catalog; kind: SiteType }) {
  const { t } = useTranslation();
  const change = useChangeType(kind.key);
  const [labels, setLabels] = useState<Texts>(() => editable(kind.labels));
  const [hidden, setHidden] = useState(kind.hidden);
  const [rows, setRows] = useState<Row[]>(() =>
    catalog.stages.map((stage) => {
      const listed = kind.stages.find((s) => s.key === stage.key);
      return {
        key: stage.key,
        listed: kind.lists_every_stage || !!listed,
        usual: !!listed?.usual,
        about: listed?.about ? editable(listed.about) : { pt: "", en: "" },
        writing: !!listed?.about,
      };
    }),
  );
  const set = (key: string, next: Partial<Row>) => setRows((was) => was.map((row) => (row.key === key ? { ...row, ...next } : row)));
  const save = () =>
    change.mutate(
      {
        labels,
        hidden,
        stages: rows
          .filter((row) => row.listed || row.usual)
          .map((row) => ({ key: row.key, usual: row.usual, about: row.about.pt.trim() ? row.about : null })),
      },
      { onSuccess: () => toast(t("admin.settings.saved")) },
    );
  const guard = useGuardedSave(save);
  // What existing projects of this type would show differently.
  const changes = () => {
    const out: string[] = [];
    if (!sameTexts(labels, kind.labels) && kind.projects)
      out.push(t("admin.settings.warning.typeName", { count: kind.projects }));
    for (const was of kind.stages) {
      const row = rows.find((r) => r.key === was.key)!;
      // "Outro" keeps only its ticked stages: unticking one drops its own words too.
      const kept = kind.lists_every_stage ? row.usual : row.listed;
      const now = kept && row.about.pt.trim() ? row.about : null;
      if (was.projects && !sameTexts(now, was.about)) {
        const name = catalog.stages.find((s) => s.key === was.key)?.titles.pt ?? was.key;
        out.push(t("admin.settings.warning.stageAbout", { name, count: was.projects }));
      }
    }
    return out;
  };
  const disabled = !catalog.can_change;
  return (
    <Panel aria-labelledby="type-title">
      <Form
        className={styles.stack}
        onSubmit={(event) => {
          event.preventDefault();
          guard.ask(changes());
        }}
      >
        <Link to=".." relative="path" className={styles.back}>
          ← {t("admin.settings.types")}
        </Link>
        <h2 id="type-title">{kind.labels.pt}</h2>
        <p className={styles.muted}>{t("admin.settings.projects", { count: kind.projects })}</p>
        <TextsFields label={t("admin.settings.typeName")} value={labels} onChange={setLabels} maxLength={catalog.limits.typeLabel!} isDisabled={disabled} />
        <ToggleSwitch label={t("admin.settings.hideType")} isSelected={hidden} onChange={setHidden} isDisabled={disabled}>
          <span className={styles.toggleText}>
            {t("admin.settings.hideType")}
            <span className={styles.muted}>{t("admin.settings.hideTypeHint")}</span>
          </span>
        </ToggleSwitch>
        <h3>{t("admin.settings.stagesOfType")}</h3>
        <p className={styles.muted}>{t(kind.lists_every_stage ? "admin.settings.outroHint" : "admin.settings.stagesOfTypeHint")}</p>
        <ul className={styles.typeStages}>
          {catalog.stages.map((stage) => {
            const row = rows.find((r) => r.key === stage.key)!;
            return (
              <li key={stage.key} data-off={!row.listed || undefined}>
                <div className={styles.typeStageHead}>
                  <strong>
                    {stage.titles.pt}
                    {stage.hidden && <span className={styles.state}>{t("admin.settings.hidden")}</span>}
                  </strong>
                  {!kind.lists_every_stage && (
                    <Checkbox
                      className={styles.check}
                      isSelected={row.listed}
                      isDisabled={disabled}
                      onChange={(listed) => set(stage.key, listed ? { listed } : { listed, usual: false })}
                    >
                      <span className={styles.box} aria-hidden="true" />
                      {t("admin.settings.listed")}
                    </Checkbox>
                  )}
                  <Checkbox
                    className={styles.check}
                    isSelected={row.usual}
                    isDisabled={disabled || !row.listed}
                    onChange={(usual) => set(stage.key, { usual })}
                  >
                    <span className={styles.box} aria-hidden="true" />
                    {t("admin.settings.usual")}
                  </Checkbox>
                </div>
                {row.listed && !kind.lists_every_stage && !row.writing && (
                  <div className={styles.generalAbout}>
                    <span className={styles.muted}>{t("admin.settings.generalAbout", { text: stage.about.pt })}</span>
                    {!disabled && (
                      <Button size="small" variant="ghost" onPress={() => set(stage.key, { writing: true })}>
                        {t("admin.settings.writeOwn")}
                      </Button>
                    )}
                  </div>
                )}
                {row.listed && !kind.lists_every_stage && row.writing && (
                  <TextsFields
                    label={t("admin.settings.ownAbout")}
                    description={t("admin.settings.generalAbout", { text: stage.about.pt })}
                    value={row.about}
                    onChange={(about) => set(stage.key, { about })}
                    maxLength={catalog.limits.stageAbout!}
                    multiline
                    isRequired={false}
                    isDisabled={disabled}
                  />
                )}
              </li>
            );
          })}
        </ul>
        <ErrorNotice error={change.error} />
        {!disabled && (
          <div className={styles.saveBar}>
            <Button type="submit" variant="primary" isDisabled={change.isPending || !labels.pt.trim()}>
              {change.isPending ? t("admin.settings.saving") : t("admin.settings.save")}
            </Button>
          </div>
        )}
      </Form>
      {guard.warning && (
        <ChangeWarning changes={guard.warning} busy={change.isPending} onConfirm={guard.confirm} onCancel={guard.cancel} />
      )}
    </Panel>
  );
}

export function StagePage() {
  const { t } = useTranslation();
  const catalog = useOutletContext<Catalog>();
  const { key = "" } = useParams();
  const stage = catalog.stages.find((found) => found.key === key);
  return stage ? <StageForm key={JSON.stringify(stage)} catalog={catalog} stage={stage} /> : <NotFound list={t("admin.settings.stages")} />;
}

function StageForm({ catalog, stage }: { catalog: Catalog; stage: SiteStage }) {
  const { t } = useTranslation();
  const change = useChangeStage(stage.key);
  const [titles, setTitles] = useState<Texts>(() => editable(stage.titles));
  const [about, setAbout] = useState<Texts>(() => editable(stage.about));
  const [hidden, setHidden] = useState(stage.hidden);
  const save = () => change.mutate({ titles, about, hidden }, { onSuccess: () => toast(t("admin.settings.saved")) });
  const guard = useGuardedSave(save);
  // Projects whose type has its own words for this stage don't show the general text.
  const own = catalog.types.reduce(
    (sum, kind) => sum + (kind.stages.find((s) => s.key === stage.key && s.about)?.projects ?? 0),
    0,
  );
  const general = stage.projects - own;
  const changes = () => {
    const out: string[] = [];
    if (!sameTexts(titles, stage.titles) && stage.projects)
      out.push(t("admin.settings.warning.stageName", { count: stage.projects }));
    if (!sameTexts(about, stage.about) && general > 0)
      out.push(t("admin.settings.warning.generalAbout", { count: general }));
    return out;
  };
  const disabled = !catalog.can_change;
  return (
    <Panel aria-labelledby="stage-title">
      <Form
        className={styles.stack}
        onSubmit={(event) => {
          event.preventDefault();
          guard.ask(changes());
        }}
      >
        <Link to=".." relative="path" className={styles.back}>
          ← {t("admin.settings.stages")}
        </Link>
        <h2 id="stage-title">{stage.titles.pt}</h2>
        <p className={styles.muted}>{t("admin.settings.projects", { count: stage.projects })}</p>
        <TextsFields label={t("admin.settings.stageName")} value={titles} onChange={setTitles} maxLength={catalog.limits.stageTitle!} isDisabled={disabled} />
        <TextsFields
          label={t("admin.settings.stageAbout")}
          description={t("admin.settings.stageAboutHint")}
          value={about}
          onChange={setAbout}
          maxLength={catalog.limits.stageAbout!}
          multiline
          isDisabled={disabled}
        />
        <ToggleSwitch label={t("admin.settings.hideStage")} isSelected={hidden} onChange={setHidden} isDisabled={disabled}>
          <span className={styles.toggleText}>
            {t("admin.settings.hideStage")}
            <span className={styles.muted}>{t("admin.settings.hideStageHint")}</span>
          </span>
        </ToggleSwitch>
        <ErrorNotice error={change.error} />
        {!disabled && (
          <div className={styles.saveBar}>
            <Button type="submit" variant="primary" isDisabled={change.isPending || !titles.pt.trim() || !about.pt.trim()}>
              {change.isPending ? t("admin.settings.saving") : t("admin.settings.save")}
            </Button>
          </div>
        )}
      </Form>
      {guard.warning && (
        <ChangeWarning changes={guard.warning} busy={change.isPending} onConfirm={guard.confirm} onCancel={guard.cancel} />
      )}
    </Panel>
  );
}
