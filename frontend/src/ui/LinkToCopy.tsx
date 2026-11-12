import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import { copyText } from "./copyText";
import styles from "./ui.module.css";

/** A link to pass on, with "Copiar link" (a WhatsApp message, say): an invite,
 *  the office's shared link, an owner's signup link. */
export function LinkToCopy({ link, label, className }: { link: string; label: string; className?: string }) {
  const { t } = useTranslation();
  return (
    <div className={[styles.linkToCopy, className].filter(Boolean).join(" ")}>
      <input aria-label={label} readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
      {/* Not copied: the link is right here, to select and copy by hand. */}
      <Button size="small" onPress={() => void copyText(link, { failed: t("copy.failed") })}>
        {t("team.copy")}
      </Button>
    </div>
  );
}
