// The browser tab's title for each screen: "Equipe · Configurações · Alinea".
// A route names its title in `handle` (catalog keys, most specific first); the
// deepest route with one wins (WCAG 2.4.2: each page says what it is).
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useMatches } from "react-router";

export type TitleHandle = { title: string[] };

export function usePageTitle(office: string | undefined) {
  const { t } = useTranslation();
  const matches = useMatches();
  const keys = [...matches].reverse().map((match) => (match.handle as TitleHandle | undefined)?.title).find(Boolean);
  const title = [...(keys ?? ["app.name"]).map((key) => t(key)), ...(office ? [office] : [])].join(" · ");
  useEffect(() => {
    document.title = title;
  }, [title]);
}
