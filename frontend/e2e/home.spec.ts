import { expect, test } from "@playwright/test";

for (const width of [320, 390, 1440]) {
  test(`public homepage works without JavaScript at ${width}px`, async ({ browser }) => {
    const context = await browser.newContext({
      javaScriptEnabled: false,
      viewport: { width, height: 900 },
      baseURL: test.info().project.use.baseURL,
    });
    const page = await context.newPage();
    try {
      const response = await page.goto("/");
      expect(response?.status()).toBe(200);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const logo = page.locator("header img");
      await expect(logo).toBeVisible();
      expect(await logo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth))
        .toBeLessThanOrEqual(width);
      await expect(page.getByRole("link", { name: "Projeto de exemplo", exact: true }))
        .toHaveAttribute("href", "/tour-projeto");
      await expect(page.getByRole("link", { name: "Ver um projeto de exemplo" }))
        .toHaveAttribute("href", "/tour-projeto");
      await page.getByRole("link", { name: "Como usamos o Google Drive" }).click();
      await expect(page.getByRole("heading", { name: "Política de Privacidade", exact: true }))
        .toBeVisible();
      await page.getByRole("link", { name: "Unio", exact: true }).click();
      await page.getByRole("link", { name: "Termos de Uso", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Termos de Uso", exact: true })).toBeVisible();
    } finally {
      await context.close();
    }
  });
}
