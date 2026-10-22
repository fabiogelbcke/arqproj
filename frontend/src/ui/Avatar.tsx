import styles from "./ui.module.css";

/** A person's first initial in a dark circle (there are no profile photos). */
export function initial(name: string): string {
  return name.trim().charAt(0).toLocaleUpperCase() || "?";
}

export function Avatar({ name }: { name: string }) {
  return (
    <span className={styles.avatar} aria-hidden="true">
      {initial(name)}
    </span>
  );
}
