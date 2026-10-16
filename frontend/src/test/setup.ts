import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

import i18next from "../i18n";

// The dialogs' tests type and click through several steps; on a busy machine
// (the full suite runs files in parallel) the default 1 s wait for what follows
// can run out. Waits still end as soon as the screen is right.
configure({ asyncUtilTimeout: 4000 });

afterEach(async () => {
  cleanup();
  await i18next.changeLanguage("pt-BR");
});
