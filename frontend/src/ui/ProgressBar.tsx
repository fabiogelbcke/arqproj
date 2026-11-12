import styles from "./ui.module.css";

/** How far an upload has got: the client page's upload bar, for every screen.
 *  `value` runs from 0 to 1; `label` names the bar for screen readers. With a
 *  `caption`, the words go above the bar with the percentage beside them
 *  ("Enviando 3 de 12…   25%"); without, it is the bar alone, for a row that
 *  already names the file. */
export function ProgressBar({
  value,
  label,
  caption,
  className,
}: {
  value: number;
  label: string;
  caption?: string;
  className?: string;
}) {
  const outer = (own: string | undefined) => [own, className].filter(Boolean).join(" "); // className: the outermost element's
  const bar = (own: string | undefined) => <progress className={own} max={1} value={value} aria-label={label} />;
  if (caption === undefined) return bar(outer(styles.progressBar));
  return (
    <div className={outer(styles.progress)}>
      <div className={styles.progressCaption} aria-live="polite">
        <span>{caption}</span>
        <span className={styles.progressPercent} aria-hidden="true">
          {Math.round(value * 100)}%
        </span>
      </div>
      {bar(styles.progressBar)}
    </div>
  );
}
