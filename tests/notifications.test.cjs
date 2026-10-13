const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('badge counts unseen updates and remembers when the panel is opened', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.PROJECT_TEST_URL, { waitUntil: 'domcontentloaded' });
    const badge = page.locator('.notifications__badge');
    assert.equal(await badge.textContent(), '3');
    assert.equal(await badge.isVisible(), true);
    await page.locator('.notifications > summary').click();
    await page.waitForFunction(() => document.querySelector('.notifications__badge').hidden);
    const link = page.locator('.project-updates__link').first();
    const target = await link.getAttribute('href');
    await link.click();
    assert.equal(new URL(page.url()).hash, target);
    assert.equal(await page.locator('.notifications').getAttribute('open'), null);
    await page.reload({ waitUntil: 'domcontentloaded' });
    assert.equal(await badge.isVisible(), false);
    // A new file revision must become unread again.
    await page.evaluate(() => {
      const key = 'arq-notifications:' + location.pathname;
      const seen = JSON.parse(localStorage.getItem(key));
      localStorage.setItem(key, JSON.stringify(seen.slice(1)));
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    assert.equal(await badge.textContent(), '1');
    assert.equal(await badge.isVisible(), true);
  } finally { await browser.close(); }
});
