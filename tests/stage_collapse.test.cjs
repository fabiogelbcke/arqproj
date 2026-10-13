const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('completed stages collapse and reopen by keyboard, timeline and search', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.STANDARD_PROJECT_TEST_URL || process.env.PROJECT_TEST_URL, { waitUntil: 'domcontentloaded' });
    const stage = page.locator('#stage-02');
    const button = stage.locator('.stage-toggle');
    assert.equal(await stage.locator('.stage__content').isVisible(), false);
    assert.equal(await page.locator('.stage--current .stage__content').isVisible(), true);
    const current = page.locator('.stage--current');
    const currentButton = current.locator('.stage-toggle');
    await currentButton.click();
    assert.equal(await current.locator('.stage__content').isVisible(), false);
    await currentButton.click();
    assert.equal(await current.locator('.stage__content').isVisible(), true);
    await page.reload({ waitUntil: 'domcontentloaded' });
    assert.equal(await currentButton.getAttribute('aria-expanded'), 'true');
    const future = page.locator('#stage-04');
    assert.equal(await future.locator('.stage__content').isVisible(), false);
    assert.equal(await future.locator('.stage-info').isVisible(), false);
    await future.locator('.stage-toggle').click();
    assert.equal(await future.locator('.stage__content').isVisible(), true);
    assert.equal(await future.locator('.stage-info').isVisible(), true);
    await future.locator('.stage-toggle').click();
    await button.focus();
    await page.keyboard.press('Enter');
    assert.equal(await stage.locator('.stage__content').isVisible(), true);
    await button.click();
    await page.locator('.timeline a[href="#stage-02"]').click();
    assert.equal(await button.getAttribute('aria-expanded'), 'true');
    await button.click();
    const name = await stage.locator('.file__name').first().textContent();
    await page.locator('#file-search').fill(name);
    assert.equal(await stage.locator('.file').first().isVisible(), true);
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
  } finally { await browser.close(); }
});
