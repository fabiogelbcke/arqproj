import { useState, type CSSProperties } from "react";

import styles from "./ui.module.css";

/** The office's logo, sized by area rather than height, so a long wordmark and a
 *  square mark look about as present: a 4:1 wordmark is the place's usual height, a
 *  squarer one taller and a longer one shorter, within the place's limits (its
 *  `--logo-*` variables), so the bar around it never grows. With a dark mode logo,
 *  each theme shows its own. */
export function OfficeLogo({
  light,
  dark,
  alt,
  className,
}: {
  light: string;
  dark?: string | null;
  alt: string;
  className?: string;
}) {
  return (
    <span className={[styles.officeLogo, className].filter(Boolean).join(" ")} data-dark={dark ? "" : undefined}>
      <Shape src={light} alt={alt} className={styles.logoLight} />
      {dark && <Shape src={dark} alt={alt} className={styles.logoDark} />}
    </span>
  );
}

function Shape({ src, alt, className }: { src: string; alt: string; className?: string }) {
  // Width over height, once loaded; until then the usual 4:1.
  const [ratio, setRatio] = useState<number | null>(null);
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      style={ratio ? ({ "--logo-r": ratio } as CSSProperties) : undefined}
      onLoad={(event) => {
        const { naturalWidth, naturalHeight } = event.currentTarget;
        if (naturalWidth && naturalHeight) setRatio(naturalWidth / naturalHeight);
      }}
    />
  );
}
