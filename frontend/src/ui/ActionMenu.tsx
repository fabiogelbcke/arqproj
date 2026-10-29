// A button that opens a short list of actions (react-aria's menu: arrow keys,
// Escape, focus back on the button). Items left out of `items` aren't shown.
import type { ReactNode } from "react";
import { Button, Menu, MenuItem, MenuTrigger, Popover } from "react-aria-components";

import styles from "./ui.module.css";

export type MenuAction = { id: string; label: string; danger?: boolean };

export function ActionMenu({
  label,
  className,
  children,
  items,
  onAction,
  placement = "bottom end",
}: {
  label: string; // the button's name for screen readers
  className?: string; // the button's look, from where it sits
  children: ReactNode; // what the button shows (an icon)
  items: MenuAction[];
  onAction: (id: string) => void;
  placement?: "bottom end" | "bottom start" | "top end";
}) {
  return (
    <MenuTrigger>
      <Button className={className} aria-label={label}>
        {children}
      </Button>
      <Popover className={styles.menuPopover} placement={placement} offset={6}>
        <Menu className={styles.menu} onAction={(key) => onAction(String(key))}>
          {items.map((item) => (
            <MenuItem key={item.id} id={item.id} className={styles.menuItem} data-danger={item.danger || undefined}>
              {item.label}
            </MenuItem>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
