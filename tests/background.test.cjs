// With Playwright installed and the local preview running:
// node --test tests/background.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('logo background follows page height without creating horizontal overflow', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.PROJECT_TEST_URL || 'http://127.0.0.1:5002/residencia-campo-alegre', { waitUntil: 'domcontentloaded' });
    if (await page.locator('html').getAttribute('data-theme') === 'dark') {
      await page.locator('.theme-toggle').click();
    }
    const asset = await page.request.get(new URL('/static/project-background.svg', page.url()).href);
    assert.equal(asset.status(), 200);
    assert.ok((await asset.text()).includes('viewBox="0 0 4461.12 4573.02"'));
    for (const width of [3440, 1920, 1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      const before = await page.evaluate(() => document.body.getBoundingClientRect().height);
      await page.evaluate(() => {
        const extra = document.createElement('div');
        extra.id = 'extra-content';
        extra.style.height = '1200px';
        document.querySelector('main').append(extra);
      });
      const result = await page.evaluate(() => {
        const style = getComputedStyle(document.body);
        return {
          height: document.body.getBoundingClientRect().height,
          image: style.backgroundImage,
          size: style.backgroundSize,
          position: style.backgroundPosition,
          repeat: style.backgroundRepeat,
          attachment: style.backgroundAttachment,
          overflow: document.documentElement.scrollWidth > innerWidth,
        };
      });
      assert.ok(result.height >= before + 1199);
      assert.ok(result.image.includes('project-background.svg'));
      assert.equal(result.size, 'cover');
      assert.equal(result.position, width < 720 ? '36.008% 100%' : '0% 100%');
      assert.equal(result.repeat, 'no-repeat');
      assert.equal(result.attachment, 'scroll');
      assert.equal(result.overflow, false);
      await page.locator('#extra-content').evaluate(el => el.remove());
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.theme-toggle').click();
    const maskPosition = await page.evaluate(() => getComputedStyle(document.body, '::after').maskPosition);
    assert.equal(maskPosition, '36.008% 100%');
  } finally {
    await browser.close();
  }
});
