// A before-and-after comparison (A46): the "after" image under the "before" one,
// which shows up to the handle. Dragging anywhere on it, or the arrow keys on its
// handle, moves the handle. Both images fill the "before" image's shape, so two
// pictures of slightly different sizes still line up as one view.
import { useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import styles from "./ui.module.css";

type Side = { src: string; label: string };

const clamp = (value: number) => Math.min(100, Math.max(0, value));

export function BeforeAfter({
  title,
  before,
  after,
  onBroken,
}: {
  title: string; // what it shows, for screen readers: "Cozinha"
  before: Side;
  after: Side;
  onBroken?: () => void; // an image didn't load (gone, or its link expired)
}) {
  const { t } = useTranslation();
  const [at, setAt] = useState(50); // the handle, in % from the left
  const [shape, setShape] = useState<number | null>(null); // the "before" image's width / height
  const frame = useRef<HTMLDivElement>(null);
  const place = (x: number) => {
    const box = frame.current?.getBoundingClientRect();
    if (box?.width) setAt(clamp(((x - box.left) / box.width) * 100));
  };
  const rounded = Math.round(at);
  return (
    <div
      ref={frame}
      className={styles.compare}
      style={{ "--at": `${at}%`, ...(shape ? { "--shape": shape } : {}) } as CSSProperties}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        place(event.clientX);
      }}
      onPointerMove={(event) => event.currentTarget.hasPointerCapture?.(event.pointerId) && place(event.clientX)}
    >
      <img className={styles.compareImage} src={after.src} alt="" draggable={false} onError={onBroken} />
      <img
        className={`${styles.compareImage} ${styles.compareBefore}`}
        src={before.src}
        alt=""
        draggable={false}
        onError={onBroken}
        onLoad={(event) => {
          const { naturalWidth: width, naturalHeight: height } = event.currentTarget;
          if (width && height) setShape(width / height);
        }}
      />
      <span className={styles.compareLabel} data-side="before" aria-hidden="true">
        {before.label}
      </span>
      <span className={styles.compareLabel} data-side="after" aria-hidden="true">
        {after.label}
      </span>
      <div
        className={styles.compareHandle}
        role="slider"
        tabIndex={0}
        aria-label={t("compare.slider", { title })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={rounded}
        aria-valuetext={t("compare.position", { before: before.label, after: after.label, shown: rounded })}
        onKeyDown={(event) => {
          const step = event.shiftKey ? 20 : 5;
          const to = {
            ArrowLeft: at - step,
            ArrowDown: at - step,
            ArrowRight: at + step,
            ArrowUp: at + step,
            Home: 0,
            End: 100,
          }[event.key];
          if (to === undefined) return;
          event.preventDefault();
          setAt(clamp(to));
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M9 7l-5 5 5 5M15 7l5 5-5 5" />
        </svg>
      </div>
    </div>
  );
}
