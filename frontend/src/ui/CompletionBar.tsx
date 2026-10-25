import styles from "./ui.module.css";

/** A thin bar filled by how many of a project's stages are completed, whatever
 *  their order (stages complete independently, 23 Oct 2026). Its label says the
 *  same in words for screen readers. */
export function CompletionBar({
  done,
  total,
  label,
}: {
  done: number;
  total: number;
  label: string;
}) {
  const share = total ? Math.min(done, total) / total : 0;
  return (
    <div
      className={styles.completionBar}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={Math.min(done, total)}
    >
      <i style={{ width: `${share * 100}%` }} />
    </div>
  );
}
