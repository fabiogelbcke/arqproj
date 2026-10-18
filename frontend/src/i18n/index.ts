// Translations: one catalog per language in backend/i18n, shared with the server
// (plan A26). Screens never contain visible text of their own.
import i18next from "i18next";
import { useEffect } from "react";
import { initReactI18next } from "react-i18next";

import en from "../../../backend/i18n/en.json";
import ptBR from "../../../backend/i18n/pt-BR.json";

export const catalogs = { "pt-BR": ptBR, en } as const;
export type Locale = keyof typeof catalogs;

void i18next.use(initReactI18next).init({
  resources: { "pt-BR": { translation: ptBR }, en: { translation: en } },
  lng: "pt-BR",
  fallbackLng: "pt-BR",
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
});

/** Switch to the office's language (from /api/tenant or /api/me). */
export function useOfficeLocale(locale: Locale | undefined): void {
  useEffect(() => {
    if (locale && i18next.language !== locale) {
      void i18next.changeLanguage(locale);
      document.documentElement.lang = locale;
    }
  }, [locale]);
}

export default i18next;
