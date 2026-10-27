import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import { toast } from "./Toast";
import styles from "./ui.module.css";

/** A link to pass on, with "Copiar link" (a WhatsApp message, say): an invite,
 *  the office's shared link, an owner's signup link. */
export function LinkToCopy({ link, label, className }: { link: string; label: string; className?: string }) {
  const { t } = useTranslation();
  return (
    <div className={[styles.linkToCopy, className].filter(Boolean).join(" ")}>
      <input aria-label={label} readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
      <Button
        size="small"
        onPress={() =>
          void navigator.clipboard?.writeText(link).then(
            () => toast(t("team.copied")),
            () => toast(link),
          )
        }
      >
        {t("team.copy")}
      </Button>
    </div>
  );
}
