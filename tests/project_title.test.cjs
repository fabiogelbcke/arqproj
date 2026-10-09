// Run with Playwright installed: node --test tests/project_title.test.cjs
// Start the local demo first; override the URL with PROJECT_TEST_URL if needed.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('complete project titles fit one line on mobile and desktop after resizing', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.goto(process.env.PROJECT_TEST_URL || 'http://127.0.0.1:5000/casa-jardim', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(resolve => setTimeout(resolve, 3000))]));
    for (const name of ['Residência Campo Alegre', 'Residência Campo Alegre — Ampliação e Reforma da Área Externa']) {
      await page.locator('.hero__title').evaluate((el, text) => { el.textContent = text; }, name);
      for (const width of [1440, 900, 720, 390, 320, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        await page.waitForFunction(() => {
          const el = document.querySelector('.hero__title');
          return el.scrollWidth <= el.clientWidth;
        });
        const result = await page.locator('.hero__title').evaluate(el => ({
          text: el.textContent,
          height: el.getBoundingClientRect().height,
          lineHeight: parseFloat(getComputedStyle(el).lineHeight),
          nowrap: getComputedStyle(el).whiteSpace,
          overflow: document.documentElement.scrollWidth > innerWidth,
        }));
        assert.equal(result.text, name);
        assert.equal(result.nowrap, 'nowrap');
        assert.ok(result.height <= result.lineHeight + 1);
        assert.equal(result.overflow, false);
      }
    }
  } finally {
    await browser.close();
  }
});
