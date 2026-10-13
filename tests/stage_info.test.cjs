const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('stage information opens by keyboard and dismisses without overflow', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.STANDARD_PROJECT_TEST_URL || process.env.PROJECT_TEST_URL, { waitUntil: 'domcontentloaded' });
    assert.equal(await page.locator('.stage-info').count(), 7);
    const first = page.locator('.stage-info').first();
    const firstStage = page.locator('.stage').filter({ has: first });
    if (!(await first.isVisible())) await firstStage.locator('.stage-toggle').click();
    for (const width of [1440, 720, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await first.locator('summary').focus();
      await page.keyboard.press('Enter');
      assert.equal(await first.locator('.stage-info__content').isVisible(), true);
      assert.match(await first.textContent(), /Proposta de serviços/);
      assert.doesNotMatch(await first.textContent(), /As entregas dependem/);
      assert.equal(await first.locator('strong').evaluate(el => getComputedStyle(el).color), 'rgb(237, 235, 169)');
      const box = await first.locator('.stage-info__content').boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= width);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.keyboard.press('Escape');
      assert.equal(await first.getAttribute('open'), null);
    }
    await first.locator('summary').click();
    await page.locator('.hero__title').click();
    assert.equal(await first.getAttribute('open'), null);
  } finally { await browser.close(); }
});
