import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { api, call } from "../api/client";
import { takeToken } from "../api/linkToken";
import { useSignedIn } from "../session/session";
import { ErrorNotice } from "../ui/ErrorNotice";
import { AuthBrand } from "./AuthBrand";
import styles from "./pages.module.css";

/** Support access (A43): the operator dashboard's one-time link, opened in the
 *  operator's browser, signs it in as Suporte Unio and goes to the projects. */
export function SupportEntryPage() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const signedIn = useSignedIn();
  const navigate = useNavigate();
  const enter = useMutation({
    mutationFn: () => call(api.POST("/api/support-session", { body: { token } })),
    onSuccess: (me) => {
      signedIn(me);
      navigate("/", { replace: true });
    },
  });
  // Once: the link works only once, and React may run an effect twice.
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    enter.mutate();
  }, [enter]);
  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        {enter.isError ? <ErrorNotice error={enter.error} /> : <p>{t("support.entering")}</p>}
      </div>
    </main>
  );
}
