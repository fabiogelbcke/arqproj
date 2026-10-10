// Requires Playwright and the local preview server.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('theme toggle persists across reloads and pages and works with the keyboard', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    const url = process.env.PROJECT_TEST_URL || 'http://127.0.0.1:5002/residencia-campo-alegre';
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      const button = page.locator('.theme-toggle');
      assert.equal(await button.isVisible(), true);
      await button.focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      assert.equal(await button.getAttribute('aria-pressed'), 'true');
      assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), 'rgb(16, 17, 17)');
      await page.reload({ waitUntil: 'domcontentloaded' });
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      await page.goto(new URL('/painel', url).href, { waitUntil: 'domcontentloaded' });
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.locator('.theme-toggle').click();
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), 'rgb(195, 208, 208)');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
  } finally {
    await browser.close();
  }
});
