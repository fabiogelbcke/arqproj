import { useCoverPhotos } from "./coverPhotos";
import { coverIndex, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

/** The project's cover, or the same placeholder photo every time: one of the
 *  bundled photos (backend/projects/covers), shown only in the painel. */
export function Cover({ project, className }: { project: ProjectSummary; className?: string }) {
  const own = project.cover_url;
  const photos = useCoverPhotos();
  const placeholder =
    Array.isArray(photos) && photos.length ? photos[coverIndex(project.id, photos.length)]!.small_url : null;
  const src = own ?? placeholder;
  return (
    <span className={[styles.cover, own ? undefined : styles.placeholder, className].filter(Boolean).join(" ")}>
      {src && <img src={src} alt="" loading="lazy" />}
    </span>
  );
}
