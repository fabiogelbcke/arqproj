// The preview page at /painel/previa (plan section 18, "Visual variants"): the real
// client project page with fictional data, and a panel that changes the data live.
// The page is drawn in a frame of the same address (`?frame`), so it can take a
// phone's width; the panel sends it each change. Nothing reaches the server.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call, setCsrfToken } from "../../api/client";
import { EXAMPLE_TIMEZONE } from "../example/fixture";
import { EXAMPLE_SLUG } from "../example/address";
import { installExampleApi } from "../example/exampleApi";
import type { Page } from "../format";
import { keepThemeUnsaved, THEME_CHANGED } from "../../ui/theme";
import { ProjectPage } from "../ProjectPage";
import { CONTROLS, KEYS, type Key, readSettings, type Settings, writeSettings } from "./settings";
import { previewData } from "./variant";

const SETTINGS = "preview-settings"; // the panel's message to the frame
const THEME = "preview-theme"; // the frame's, when the page's own theme switch is used

/** The panel, and the page in its frame. */
export function PreviewApp() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState(() => readSettings(window.location.search));
  const frame = useRef<HTMLIFrameElement>(null);
  // The frame starts from the address; later changes go to it as messages.
  const [source] = useState(() => `${window.location.pathname}?${["frame", writeSettings(settings)].filter(Boolean).join("&")}`);
  useEffect(() => {
    document.title = t("preview.title");
  }, [t]);

  const change = <K extends Key>(key: K, value: Settings[K]) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    const query = writeSettings(next);
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
    frame.current?.contentWindow?.postMessage({ type: SETTINGS, settings: next }, window.location.origin);
  };
  // The page's own theme switch, used in the frame: the panel and the address follow
  // (the frame already shows it).
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.data?.type !== THEME) return;
      const theme = event.data.theme === "dark" ? "dark" : "light";
      setSettings((current) => {
        const next = { ...current, theme } as Settings;
        const query = writeSettings(next);
        window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
        return next;
      });
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, []);

  return (
    <div className="preview">
      <form className="preview-panel" aria-label={t("preview.panel")} onSubmit={(event) => event.preventDefault()}>
        <h1>{t("preview.title")}</h1>
        <p className="preview-hint">{t("preview.hint")}</p>
        {KEYS.map((key) => (
          <Control key={key} name={key} value={settings[key]} onChange={(value) => change(key, value as never)} />
        ))}
      </form>
      <div className={`preview-stage preview-${settings.width}`}>
        <iframe ref={frame} src={source} title={t("preview.frame")} />
      </div>
    </div>
  );
}

function Control({ name, value, onChange }: { name: Key; value: Settings[Key]; onChange: (value: unknown) => void }) {
  const { t } = useTranslation();
  const control = CONTROLS[name];
  const label = t(`preview.controls.${name}`);
  if (control.kind === "toggle")
    return (
      <label className="preview-toggle">
        <input type="checkbox" checked={value as boolean} onChange={(event) => onChange(event.target.checked)} />
        {label}
      </label>
    );
  if (control.kind === "range")
    return (
      <label className="preview-range">
        <span>
          {label} <output>{value as number}</output>
        </span>
        <input
          type="range"
          min={control.min}
          max={control.max}
          step={control.step}
          value={value as number}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </label>
    );
  return (
    <fieldset className="preview-choice">
      <legend>{label}</legend>
      {control.options.map((option: string) => (
        <label key={option}>
          <input type="radio" name={name} checked={value === option} onChange={() => onChange(option)} />
          {t(`preview.options.${option}`)}
        </label>
      ))}
    </fieldset>
  );
}

/** The page itself, in the frame: drawn again for each setting the panel sends. */
export function PreviewFrame() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState(() => readSettings(window.location.search));
  const [page, setPage] = useState<Page | null>(null);
  const [drawn, setDrawn] = useState(0); // a new page component for each change of data

  useEffect(() => {
    keepThemeUnsaved(); // the preview's theme is the address's, not this device's choice
    const receive = (event: MessageEvent) => {
      if (event.origin === window.location.origin && event.data?.type === SETTINGS) setSettings(event.data.settings);
    };
    // The page's own theme switch: the panel is told, so its control and the address follow.
    const tell = () =>
      window.parent.postMessage({ type: THEME, theme: document.documentElement.dataset.theme }, window.location.origin);
    window.addEventListener("message", receive);
    window.addEventListener(THEME_CHANGED, tell);
    return () => {
      window.removeEventListener("message", receive);
      window.removeEventListener(THEME_CHANGED, tell);
    };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = settings.theme; // this frame only: not saved
    installExampleApi(new Date(), previewData(settings, new Date(), EXAMPLE_TIMEZONE));
    if (settings.view === "staff") setCsrfToken("previa");
    void call(api.GET("/api/pages/{slug}", { params: { path: { slug: EXAMPLE_SLUG } } })).then((next) => {
      setPage(next);
      setDrawn((n) => n + 1);
    });
  }, [settings]);

  if (!page) return <p className="sr">{t("page.loading")}</p>;
  return (
    <ProjectPage
      key={drawn}
      page={page}
      slug={EXAMPLE_SLUG}
      ready={page.staff != null}
      onChanged={() =>
        // An edit tried in the staff view: the page again, from the edited data.
        void call(api.GET("/api/pages/{slug}", { params: { path: { slug: EXAMPLE_SLUG } } })).then(setPage)
      }
    />
  );
}
