import unio from "../assets/unio.png";
import unioDark from "../assets/unio-dark.png";
import styles from "./ui.module.css";

/** Unio's logo, dark letters or (dark theme) light ones; its height comes from
 *  where it sits (`className` sizes `img`). */
export function UnioMark({ className }: { className?: string }) {
  return (
    <span className={[styles.unioMark, className].filter(Boolean).join(" ")}>
      <img className={styles.unioLight} src={unio} alt="Unio" />
      <img className={styles.unioDark} src={unioDark} alt="Unio" />
    </span>
  );
}

/** At the foot of the painel and of a project's page: quietly, whose product it is. */
export function UnioFooter({ className }: { className?: string }) {
  return (
    <a className={[styles.unioFooter, className].filter(Boolean).join(" ")} href="https://myunio.app/">
      <UnioMark />
    </a>
  );
}
