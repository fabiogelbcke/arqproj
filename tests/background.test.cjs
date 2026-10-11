const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
test('plain backgrounds stay uniform in both themes and screen sizes', async () => {
  const browser = await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL});
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.goto(process.env.PROJECT_TEST_URL,{waitUntil:'domcontentloaded'});
    for(const theme of ['light','dark']) {
      if(await page.locator('html').getAttribute('data-theme')!==theme) await page.locator('.theme-toggle').click();
      for(const width of [1920,1440,390,320]) {
        await page.setViewportSize({width,height:900});
        await page.waitForTimeout(150);
        const style=await page.evaluate(()=>({color:getComputedStyle(document.body).backgroundColor,image:getComputedStyle(document.body).backgroundImage,before:getComputedStyle(document.body,'::before').content,after:getComputedStyle(document.body,'::after').content,overflow:document.documentElement.scrollWidth>innerWidth}));
        assert.equal(style.color,theme==='light'?'rgb(244, 244, 244)':'rgb(16, 17, 17)');
        assert.equal(style.image,'none');
        assert.equal(style.before,'none');
        assert.equal(style.after,'none');
        assert.equal(style.overflow,false);
      }
    }
  } finally { await browser.close(); }
});
