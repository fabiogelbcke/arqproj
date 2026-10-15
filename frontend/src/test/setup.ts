import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import i18next from "../i18n";

afterEach(async () => {
  cleanup();
  await i18next.changeLanguage("pt-BR");
});
