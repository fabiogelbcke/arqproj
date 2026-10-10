// With Playwright installed and the meeting sample running:
// PROJECT_TEST_URL=http://127.0.0.1:5002/casa-jardim node --test tests/meeting.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('meeting card and calendar dates work on desktop and mobile', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    const url = process.env.PROJECT_TEST_URL || 'http://127.0.0.1:5002/casa-jardim';
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    const card = page.locator('.meeting');
    const link = card.locator('a[href^="https://calendar.google.com/"]');
    const calendarButton = card.locator('.meeting__calendar summary');
    assert.equal(await link.isVisible(), false);
    await calendarButton.focus();
    await page.keyboard.press('Enter');
    assert.equal(await link.isVisible(), true);
    const params = new URL(await link.getAttribute('href')).searchParams;
    assert.equal(params.get('action'), 'TEMPLATE');
    assert.equal(params.get('text'), await card.locator('.meeting__title').textContent());
    const times = await card.locator('time').evaluateAll(elements => elements.map(el => el.dateTime));
    const format = value => new Date(value).toISOString().replace(/[-:]/g, '').replace('.000', '');
    assert.equal(params.get('dates'), times.map(format).join('/'));
    const apple = card.locator('a[href$="/reuniao.ics"]');
    const response = await page.request.get(new URL(await apple.getAttribute('href'), url).href);
    assert.equal(response.status(), 200);
    assert.ok(response.headers()['content-type'].startsWith('text/calendar'));
    assert.ok((await response.text()).includes('BEGIN:VEVENT'));
    assert.equal(await calendarButton.evaluate(el => getComputedStyle(el).backgroundColor),
      await page.evaluate(() => {
        const probe = document.createElement('span');
        probe.style.backgroundColor = 'var(--accent)';
        document.body.append(probe);
        const color = getComputedStyle(probe).backgroundColor;
        probe.remove();
        return color;
      }));
    for (const width of [1440, 900, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await link.isVisible(), true);
      const meetingBox = await card.boundingBox();
      const timelineBox = await page.locator('.timeline').boundingBox();
      assert.ok(meetingBox.y + meetingBox.height <= timelineBox.y);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
    await page.goto(new URL('/loja-centro-k3x9', url).href, { waitUntil: 'domcontentloaded' });
    assert.ok(await page.locator('.meeting--empty').isVisible());
    assert.equal(await page.locator('.meeting a').count(), 0);
  } finally {
    await browser.close();
  }
});
