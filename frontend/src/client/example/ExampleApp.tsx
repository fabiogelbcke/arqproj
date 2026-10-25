// The example project at /tour-projeto (plan section 16, "Onboarding help"): a project
// page filled with fictional content in the browser. Nothing is in the office's
// Drive and nothing is saved (exampleApi.ts); it works before Drive is connected.
// Signed-in staff get the staff bar, to try edit mode; others, the client's view.
// To remove it: this folder, its line in main.tsx and in Primeiros passos, and the
// reserved address (RESERVED_SLUGS).
import "./example.css";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call } from "../../api/client";
import i18next, { useOfficeLocale } from "../../i18n";
import type { Page } from "../format";
import { ProjectPage } from "../ProjectPage";
import { signOut } from "../signOut";
import { EXAMPLE_SLUG } from "./address";
import { installExampleApi } from "./exampleApi";
import { startExploreTour } from "./ExploreTour";

export function ExampleApp() {
  const { t } = useTranslation();
  // Before the page's first request, and afresh on every visit.
  useState(() => installExampleApi());
  const [page, setPage] = useState<Page | null>(null);
  const [signedIn, setSignedIn] = useState<boolean | null>(null); // null: not known yet
  // Who is signed in, for the header menu, as on the office's own project pages.
  const [person, setPerson] = useState<{ name: string; email: string } | null>(null);
  const [version, setVersion] = useState(0); // bumped to draw the page again after a change
  useOfficeLocale(page?.locale);

  useEffect(() => {
    // Staff (who see the staff bar), and the office's name and logo for the header.
    void Promise.all([
      call(api.GET("/api/me")).then(
        (me) => {
          setPerson({ name: me.name, email: me.email });
          return true;
        },
        () => false,
      ),
      call(api.GET("/api/tenant")).catch(() => undefined),
    ]).then(([staff]) => setSignedIn(staff));
  }, []);
  useEffect(() => {
    if (signedIn === null) return;
    void call(api.GET("/api/pages/{slug}", { params: { path: { slug: EXAMPLE_SLUG } } })).then(setPage);
  }, [signedIn, version]);

  // In the office's language as it is now: this render's `t` may predate it.
  const tour = () => void startExploreTour(i18next.t);
  const toured = useRef(false);
  useEffect(() => {
    if (!page || toured.current) return;
    toured.current = true; // once per visit, however often the page is drawn
    tour();
  }, [page]);

  if (!page) return <p className="sr">{t("page.loading")}</p>;
  return (
    <>
      <aside className="example-banner" aria-label={t("example.banner")}>
        <strong>{t("example.banner")}</strong> <span>{t("example.bannerHint")}</span>
      </aside>
      <ProjectPage
        page={page}
        slug={EXAMPLE_SLUG}
        sharing={false} // no links from the example: it never reaches the server
        ready={signedIn === true}
        person={person}
        onSignOut={signOut}
        onChanged={() => setVersion((v) => v + 1)}
        onTour={tour}
      />
    </>
  );
}
