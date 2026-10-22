import { useRef, useState, type DetailsHTMLAttributes } from "react";

import { useDismiss } from "./useDismiss";

/** A `<details>` whose content pops over the page (a small menu): it closes,
 *  like our other menus, on a click outside it or Esc. */
export function PopoverDetails({ onToggle, ...props }: DetailsHTMLAttributes<HTMLDetailsElement>) {
  const ref = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  useDismiss(ref, open, () => ref.current?.removeAttribute("open"));
  return (
    <details
      ref={ref}
      {...props}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
        onToggle?.(event);
      }}
    />
  );
}
