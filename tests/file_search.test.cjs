const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('file search filters names and restores stages when cleared', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.PROJECT_TEST_URL, { waitUntil: 'domcontentloaded' });
    const search = page.locator('#file-search');
    await page.setViewportSize({ width: 1440, height: 900 });
    const searchBox = await search.boundingBox();
    const headerBox = await page.locator('.stage__header').first().boundingBox();
    assert.ok(Math.abs(searchBox.y - headerBox.y) <= 1);
    const total = await page.locator('.file').count();
    assert.ok(total > 1);
    const name = await page.locator('.file__name').first().textContent();
    await search.fill(name.toUpperCase());
    assert.ok(await page.locator('.file:visible').count() > 0);
    assert.ok(await page.locator('.file:visible').count() < total);
    await search.fill('arquivo-inexistente-987654321');
    assert.equal(await page.locator('.file:visible').count(), 0);
    assert.equal(await page.locator('.file-search__empty').isVisible(), true);
    await search.fill('');
    assert.equal(await page.locator('.file:visible').count(), total);
    assert.equal(await page.locator('.file-search__empty').isVisible(), false);
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
  } finally { await browser.close(); }
});
