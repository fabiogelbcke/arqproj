// The meeting editor's day and times (Fabio, 20 Oct 2026: a nicer picker than the
// browser's own boxes): React Aria's date picker, with a month to choose from, and
// its time field, in the office's language. The values stay the API's strings,
// "2026-10-21" and "16:00", so the editor's form and request don't change.
import { parseDate, parseTime } from "@internationalized/date";
import {
  Button,
  Calendar,
  CalendarCell,
  CalendarGrid,
  DateInput,
  DatePicker,
  DateSegment,
  Dialog,
  Group,
  Heading,
  I18nProvider,
  Label,
  Popover,
  TimeField,
} from "react-aria-components";
import { useTranslation } from "react-i18next";

const pad = (n: number) => String(n).padStart(2, "0");

/** A day as "YYYY-MM-DD" ("" for none). */
export function DayField({ label, value, onChange }: { label: string; value: string; onChange: (day: string) => void }) {
  const { t, i18n } = useTranslation();
  return (
    <I18nProvider locale={i18n.language}>
      <DatePicker
        className="field when"
        value={value ? parseDate(value) : null}
        onChange={(day) => onChange(day ? day.toString() : "")}
        isRequired
        shouldForceLeadingZeros
      >
        <Label>{label}</Label>
        <Group className="input when__box">
          <DateInput className="when__input">{(segment) => <DateSegment className="when__segment" segment={segment} />}</DateInput>
          <Button className="when__open" aria-label={t("edit.chooseDay")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M4 7h16v13H4zM4 11h16M8 4v4M16 4v4" />
            </svg>
          </Button>
        </Group>
        <Popover className="when__popover" placement="bottom start">
          <Dialog className="when__dialog">
            <Calendar className="when__calendar">
              <header className="when__month">
                <Button slot="previous" className="when__nav">
                  ‹
                </Button>
                <Heading />
                <Button slot="next" className="when__nav">
                  ›
                </Button>
              </header>
              <CalendarGrid className="when__grid">{(date) => <CalendarCell className="when__day" date={date} />}</CalendarGrid>
            </Calendar>
          </Dialog>
        </Popover>
      </DatePicker>
    </I18nProvider>
  );
}

/** A time of day as "HH:MM" ("" for none). */
export function TimeOfDayField({
  label,
  value,
  onChange,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (time: string) => void;
  required?: boolean;
}) {
  const { i18n } = useTranslation();
  return (
    <I18nProvider locale={i18n.language}>
      <TimeField
        className="field when"
        value={value ? parseTime(value) : null}
        onChange={(time) => onChange(time ? `${pad(time.hour)}:${pad(time.minute)}` : "")}
        isRequired={required}
        shouldForceLeadingZeros
      >
        <Label>{label}</Label>
        <DateInput className="input when__box when__input">
          {(segment) => <DateSegment className="when__segment" segment={segment} />}
        </DateInput>
      </TimeField>
    </I18nProvider>
  );
}
