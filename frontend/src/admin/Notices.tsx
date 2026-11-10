// "Configurações" → "Avisos" (A48): how clients' updates and meeting reminders
// go, for every office. Only the values: the messages' words are Meta's to approve.
import { useState } from "react";
import { Checkbox, Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { Panel } from "../ui/Panel";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import styles from "./admin.module.css";
import { NEWS, useChangeNotices, useNotices, type Notices } from "./siteSettings";

export function NoticesPage() {
  const { t } = useTranslation();
  const notices = useNotices();
  if (notices.isPending) return <p className={styles.muted}>{t("app.loading")}</p>;
  if (!notices.data) return <ErrorNotice error={notices.error} />;
  // A fresh form whenever the saved values change (its own save included).
  return <NoticesForm key={JSON.stringify(notices.data)} saved={notices.data} />;
}

type Numbers = "quiet_minutes" | "hold_minutes" | "reminder_before_minutes" | "ask_again_days";
type Limits = "quietMinutes" | "holdMinutes" | "reminderBeforeMinutes" | "askAgainDays";

function NoticesForm({ saved }: { saved: Notices }) {
  const { t } = useTranslation();
  const change = useChangeNotices();
  const [values, setValues] = useState(saved);
  const [typed, setTyped] = useState<Record<Numbers, string>>({
    quiet_minutes: String(saved.quiet_minutes),
    hold_minutes: String(saved.hold_minutes),
    reminder_before_minutes: String(saved.reminder_before_minutes),
    ask_again_days: String(saved.ask_again_days),
  });
  const disabled = !saved.can_change;
  const number = (name: Numbers, limit: Limits, label: string, hint: string) => {
    const [least, most] = saved.limits[limit] ?? [];
    return (
      <TextField
        label={label}
        description={`${hint} ${t("admin.notices.between", { least, most })}`}
        type="number"
        inputMode="numeric"
        value={typed[name]}
        onChange={(value) => setTyped((was) => ({ ...was, [name]: value }))}
        isRequired
        isDisabled={disabled}
      />
    );
  };
  const whole = Object.values(typed).every((value) => /^\d+$/.test(value.trim()));
  const save = () =>
    change.mutate(
      {
        ...values,
        quiet_minutes: Number(typed.quiet_minutes),
        hold_minutes: Number(typed.hold_minutes),
        reminder_before_minutes: Number(typed.reminder_before_minutes),
        ask_again_days: Number(typed.ask_again_days),
      },
      { onSuccess: () => toast(t("admin.settings.saved")) },
    );
  const toggle = (news: (typeof NEWS)[number], on: boolean) =>
    setValues((was) => ({
      ...was,
      whatsapp_news: on ? [...was.whatsapp_news, news] : was.whatsapp_news.filter((n) => n !== news),
    }));
  return (
    <Panel aria-labelledby="notices-title">
      <Form
        className={styles.stack}
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <h2 id="notices-title">{t("admin.notices.title")}</h2>
        <p className={styles.muted}>{t("admin.notices.intro")}</p>

        <h3>{t("admin.notices.updates")}</h3>
        {number("quiet_minutes", "quietMinutes", t("admin.notices.quiet"), t("admin.notices.quietHint"))}
        {number("hold_minutes", "holdMinutes", t("admin.notices.hold"), t("admin.notices.holdHint"))}

        <h3>{t("admin.notices.reminders")}</h3>
        <TextField
          label={t("admin.notices.morning")}
          description={t("admin.notices.morningHint")}
          type="time"
          value={values.reminder_morning}
          onChange={(reminder_morning) => setValues((was) => ({ ...was, reminder_morning }))}
          isRequired
          isDisabled={disabled}
        />
        <TextField
          label={t("admin.notices.evening")}
          description={t("admin.notices.eveningHint")}
          type="time"
          value={values.reminder_evening}
          onChange={(reminder_evening) => setValues((was) => ({ ...was, reminder_evening }))}
          isRequired
          isDisabled={disabled}
        />
        {number("reminder_before_minutes", "reminderBeforeMinutes", t("admin.notices.before"), t("admin.notices.beforeHint"))}

        <h3>{t("admin.notices.whatsapp")}</h3>
        {number("ask_again_days", "askAgainDays", t("admin.notices.askAgain"), t("admin.notices.askAgainHint"))}
        <fieldset className={styles.texts} disabled={disabled}>
          <legend>{t("admin.notices.news")}</legend>
          <p className={styles.muted}>{t("admin.notices.newsHint")}</p>
          <div className={styles.stack}>
            {NEWS.map((news) => (
              <Checkbox
                key={news}
                className={styles.check}
                isSelected={values.whatsapp_news.includes(news)}
                isDisabled={disabled}
                onChange={(on) => toggle(news, on)}
              >
                <span className={styles.box} aria-hidden="true" />
                {t(`admin.notices.kind.${news}`)}
              </Checkbox>
            ))}
          </div>
        </fieldset>

        <ErrorNotice error={change.error} />
        {!disabled && (
          <div className={styles.saveBar}>
            <Button type="submit" variant="primary" isDisabled={change.isPending || !whole}>
              {change.isPending ? t("admin.settings.saving") : t("admin.settings.save")}
            </Button>
          </div>
        )}
      </Form>
    </Panel>
  );
}
