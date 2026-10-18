import type { ReactNode } from "react";
import { Dialog, DialogTrigger, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EXAMPLE_SLUG } from "../client/example/address";
import { OfficeDetails } from "../pages/SettingsOfficePage";
import { NewProjectDialog } from "../projects/NewProjectDialog";
import dialogs from "../projects/projects.module.css";
import { useMe } from "../session/session";
import styles from "../pages/pages.module.css";
import { Button } from "../ui/Button";
import { CloseButton } from "../ui/CloseButton";
import { toast } from "../ui/Toast";
import { useOnboarding } from "./drive";
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
  // Not one of the steps: the example project stays at hand once they are done.
  const example = (
    <a className={styles.exampleLink} href={`/${EXAMPLE_SLUG}`}>
      {t("firstSteps.example")}
    </a>
  );
  if (steps.storage_connected && steps.office_details && steps.has_project)
    return <p className={styles.exampleAfter}>{example}</p>;
  const owner = me.data?.role === "owner";
  const done = [steps.storage_connected, steps.office_details, steps.has_project].filter(Boolean).length;
  const total = 3;
  const action = (finished: boolean | undefined, control: ReactNode) =>
    finished ? <span className={styles.stepDone}>{t("firstSteps.done")}</span> : owner ? control : null;
  return (
    <section className={styles.steps} aria-labelledby="first-steps">
      <div className={styles.stepsHead}>
        <h2 id="first-steps">{t("firstSteps.title")}</h2>
        <span className={styles.stepsCount} aria-label={t("firstSteps.progressLabel", { done, total })}>
          {t("firstSteps.progress", { done, total })}
        </span>
      </div>
      <div className={styles.stepsBar} aria-hidden="true">
        <i style={{ width: `${(done / total) * 100}%` }} />
      </div>
      <ol>
        <Step
          done={steps.storage_connected}
          icon={driveIcon}
          title={t("firstSteps.storage")}
          hint={t("firstSteps.storageHint")}
          action={action(
            steps.storage_connected,
            <Link className={styles.stepAction} to="/configuracoes/drive">
              {t("firstSteps.storageAction")}
            </Link>,
          )}
        />
        <Step
          done={steps.office_details}
          title={t("firstSteps.office")}
          hint={t("firstSteps.officeHint")}
          action={action(
            steps.office_details,
            <OfficeDialog />,
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
      <p className={styles.exampleLine}>{example}</p>
      {!owner && <p className={styles.small}>{t("firstSteps.membersNote")}</p>}
    </section>
  );
}

/** The office's details in a dialog, so the first steps don't leave the page. */
function OfficeDialog() {
  const { t } = useTranslation();
  return (
    <DialogTrigger>
      <Button variant="primary" className={styles.stepAction}>
        {t("firstSteps.officeAction")}
      </Button>
      <ModalOverlay className={dialogs.overlay} isDismissable>
        <Modal className={dialogs.modal}>
          <Dialog className={dialogs.dialog}>
            {({ close }) => (
              <>
                <Heading slot="title" className={dialogs.dialogTitle}>
                  {t("firstSteps.officeDialogTitle")}
                </Heading>
                <CloseButton onPress={close} />
                <OfficeDetails onSaved={close} />
              </>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
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
  hint: string;
  action: ReactNode;
}) {
  return (
    <li className={styles.step} data-done={done || undefined}>
      {/* A box that ticks itself; for screen readers the "Concluído" beside it says it. */}
      <span className={styles.stepBox} aria-hidden="true" />
      <span className={styles.stepText}>
        <strong>
          {title}
          {icon && <img className={styles.stepIcon} src={icon} alt="" />}
        </strong>
        <small>{hint}</small>
      </span>
      {action}
    </li>
  );
}
