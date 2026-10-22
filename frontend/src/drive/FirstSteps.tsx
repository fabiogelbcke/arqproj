import type { ReactNode } from "react";
import { DialogTrigger } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { EXAMPLE_SLUG } from "../client/example/address";
import { DriveDetails } from "../pages/SettingsDrivePage";
import { OfficeDetails } from "../pages/SettingsOfficePage";
import { NewProjectDialog } from "../projects/NewProjectDialog";
import { useMe } from "../session/session";
import styles from "../pages/pages.module.css";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { InfoTip } from "../ui/InfoTip";
import { toast } from "../ui/Toast";
import { useOnboarding } from "./drive";
// A pale roof and sky behind the invitation to the example project.
import exampleBand from "../client/example/images/convite.jpg";
// Google's own Drive icon, unaltered (Google's branding rules for "connect to Drive").
import driveIcon from "./google-drive.png";

/** What a new office still has to do; gone once everything is done. Each box
 *  ticks itself when its step is done: it shows progress, it isn't a control. */
export function FirstSteps() {
  const { t } = useTranslation();
  const onboarding = useOnboarding();
  const me = useMe();
  const steps = onboarding.data;
  if (!steps) return null;
  // Once the steps are done, the example project stays at hand as a line.
  if (steps.storage_connected && steps.office_details && steps.has_project)
    return (
      <p className={styles.exampleAfter}>
        <a className={styles.exampleLink} href={`/${EXAMPLE_SLUG}`}>
          {t("firstSteps.example")}
        </a>
      </p>
    );
  const owner = me.data?.role === "owner";
  const done = [steps.storage_connected, steps.office_details, steps.has_project].filter(Boolean).length;
  const total = 3;
  const action = (finished: boolean | undefined, control: ReactNode) =>
    finished ? <span className={styles.stepDone}>{t("firstSteps.done")}</span> : owner ? control : null;
  return (
    <section className={styles.steps} aria-labelledby="first-steps" data-tour="first-steps">
      <div className={styles.stepsHead}>
        <h2 id="first-steps">{t("firstSteps.title")}</h2>
        <span className={styles.stepsCount} aria-label={t("firstSteps.progressLabel", { done, total })}>
          {t("firstSteps.progress", { done, total })}
        </span>
      </div>
      <div className={styles.stepsBar} aria-hidden="true">
        <i style={{ width: `${(done / total) * 100}%` }} />
      </div>
      {/* Not a step: first, so a phone shows it before the steps fill the screen
          (plan section 16). A new office's own first page will look empty. */}
      <a className={styles.exampleInvite} href={`/${EXAMPLE_SLUG}`}>
        <img src={exampleBand} alt="" />
        <span>{t("firstSteps.exampleIntro")}</span>
        <strong>{t("firstSteps.exampleAction")} →</strong>
      </a>
      <ol>
        <Step
          done={steps.storage_connected}
          icon={driveIcon}
          title={t("firstSteps.storage")}
          hint={t("firstSteps.storageHint")}
          action={action(
            steps.storage_connected,
            <StepDialog label={t("firstSteps.storageAction")} title={t("firstSteps.storageDialogTitle")}>
              {() => <DriveDetails />}
            </StepDialog>,
          )}
        />
        <Step
          done={steps.office_details}
          title={t("firstSteps.office")}
          hint={t("firstSteps.officeHint")}
          action={action(
            steps.office_details,
            <StepDialog label={t("firstSteps.officeAction")} title={t("firstSteps.officeDialogTitle")}>
              {(close) => <OfficeDetails onSaved={close} />}
            </StepDialog>,
          )}
        />
        <Step
          done={steps.has_project}
          title={t("firstSteps.firstProject")}
          hint={t("firstSteps.firstProjectHint")}
          action={action(
            steps.has_project,
            <NewProjectDialog
              trigger={{ label: t("firstSteps.firstProjectAction"), className: styles.stepAction ?? "" }}
              onCreated={(project) => toast(t("newProject.created", { name: project.name }))}
            />,
          )}
        />
      </ol>
      {!owner && <p className={styles.small}>{t("firstSteps.membersNote")}</p>}
    </section>
  );
}

/** A step's settings in a dialog, so the first steps don't leave the page. */
function StepDialog({
  label,
  title,
  children,
}: {
  label: string;
  title: string;
  children: (close: () => void) => ReactNode;
}) {
  return (
    <DialogTrigger>
      <Button variant="primary" className={styles.stepAction}>
        {label}
      </Button>
      <DialogFrame title={title}>{children}</DialogFrame>
    </DialogTrigger>
  );
}

function Step({
  done,
  icon,
  title,
  hint,
  action,
}: {
  done?: boolean;
  icon?: string; // after the title
  title: string;
  hint: string; // what the step means, behind its ⓘ
  action: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <li className={styles.step} data-done={done || undefined}>
      {/* A box that ticks itself; for screen readers the "Concluído" beside it says it. */}
      <span className={styles.stepBox} aria-hidden="true" />
      <span className={styles.stepTitle}>
        {title}
        {icon && <img className={styles.stepIcon} src={icon} alt="" />}
      </span>
      <InfoTip label={t("firstSteps.about", { step: title })}>{hint}</InfoTip>
      {action}
    </li>
  );
}
