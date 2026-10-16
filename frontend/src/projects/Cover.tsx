import { coverIndex, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

// 10 CC0 photos (StockSnap; see covers/LICENSES.json) for projects without a cover.
const PLACEHOLDERS = Object.values(
  import.meta.glob<string>("./covers/*.jpg", { eager: true, import: "default", query: "?url" }),
).sort();

/** The project's cover, or the same placeholder photo every time. */
export function Cover({ project, className }: { project: ProjectSummary; className?: string }) {
  const own = project.cover_url;
  return (
    <span className={[styles.cover, own ? undefined : styles.placeholder, className].filter(Boolean).join(" ")}>
      <img src={own ?? PLACEHOLDERS[coverIndex(project.id, PLACEHOLDERS.length)]} alt="" loading="lazy" />
    </span>
  );
}
