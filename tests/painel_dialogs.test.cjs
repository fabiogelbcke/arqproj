// Requires Playwright and the local preview server (with the fake Google sign-in).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('painel: connect, name the folder, create a project and edit settings in modals', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    const url = process.env.PAINEL_TEST_URL;
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.fill('input[name="password"]', 'demo');
    await page.press('input[name="password"]', 'Enter');
    await page.waitForSelector('.drive-banner');

    // Connect opens a modal on the same page; Escape and Cancel close it.
    await page.click('.drive-banner [data-open-dialog="connect-dialog"]');
    const connect = page.locator('#connect-dialog');
    assert.equal(await connect.isVisible(), true);
    assert.equal(await page.inputValue('#connect-folder-name'), 'Portal Clientes');
    await page.keyboard.press('Escape');
    assert.equal(await connect.isVisible(), false);
    await page.click('.drive-banner [data-open-dialog="connect-dialog"]');
    await page.fill('#connect-folder-name', 'Entregas Teste');
    await page.click('#connect-dialog button[type="submit"]');

    // The fake consent page, then straight back with the folder already created.
    await page.click('a.allow');
    await page.waitForSelector('.drive-projects');
    assert.match(await page.textContent('body'), /Entregas Teste/);
    assert.equal(await page.locator('#folder-dialog').count(), 0);

    // New project: the stage list can be edited before creating.
    await page.click('[data-open-dialog="project-dialog"]');
    await page.fill('#project-title', 'Casa Árvore');
    assert.equal(await page.getAttribute('#project-slug', 'placeholder'), 'casa-arvore');
    const stages = page.locator('#project-dialog [data-stage-list] li');
    const before = await stages.count();
    await stages.first().locator('[data-remove-stage]').click();
    await page.click('#project-dialog [data-add-stage]');
    await page.keyboard.type('Pós-obra');
    assert.equal(await stages.count(), before);
    // The link converts as you type; the last stage can't be removed.
    await page.fill('#project-slug', '');
    await page.type('#project-slug', 'Casa Árvore 2');
    assert.equal(await page.inputValue('#project-slug'), 'casa-arvore-2');
    await page.fill('#project-slug', '');
    assert.equal(await stages.last().locator('input').inputValue(), 'Pós-obra');
    await page.click('#project-dialog button[type="submit"]');
    await page.waitForSelector('.drive-projects__title');
    assert.equal(await page.textContent('.drive-projects__title'), 'Casa Árvore');

    // The same name again is flagged before submitting, whatever the case.
    await page.click('[data-open-dialog="project-dialog"]');
    await page.fill('#project-title', 'casa árvore');
    assert.notEqual(await page.$eval('#project-title', el => el.validationMessage), '');
    await page.fill('#project-title', 'Outra Casa');
    assert.equal(await page.$eval('#project-title', el => el.validationMessage), '');
    await page.fill('#project-slug', 'casa-arvore');
    assert.notEqual(await page.$eval('#project-slug', el => el.validationMessage), '');
    await page.keyboard.press('Escape');

    // Settings modal fits a phone screen and saves the office name.
    await page.setViewportSize({ width: 390, height: 800 });
    await page.click('[data-open-dialog="settings-dialog"]');
    assert.equal(await page.locator('#settings-dialog').isVisible(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.equal(await page.textContent('[data-file-name]'), 'Nenhum arquivo escolhido');
    await page.fill('#settings-name', 'Escritório Renomeado');
    await page.click('#settings-dialog form[enctype] button[type="submit"]');
    await page.waitForSelector('.flash');
    assert.match(await page.title(), /Escritório Renomeado/);
    assert.match(await page.textContent('.site-footer'), /Escritório Renomeado/);
  } finally {
    await browser.close();
  }
});

test('painel: the last stage cannot be removed', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.setContent(`
      <ol data-stage-list data-last-stage-label="needs one">
        <li><input name="stage"><button type="button" data-remove-stage aria-label="remove">x</button></li>
        <li><input name="stage"><button type="button" data-remove-stage aria-label="remove">x</button></li>
      </ol>
      <script>${require('node:fs').readFileSync(require('node:path').join(__dirname, '../static/painel-dialogs.js'), 'utf8')}</script>`);
    await page.evaluate(() => document.dispatchEvent(new Event('DOMContentLoaded')));
    await page.locator('[data-remove-stage]').first().click();
    const last = page.locator('[data-remove-stage]');
    assert.equal(await last.count(), 1);
    assert.equal(await last.isDisabled(), true);
  } finally {
    await browser.close();
  }
});

test('painel: the projects-folder modal cannot be dismissed', async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    const page = await browser.newPage();
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.setContent(`
      <dialog id="folder-dialog" data-required data-open-on-load><p>required</p></dialog>
      <script>${require('node:fs').readFileSync(require('node:path').join(__dirname, '../static/painel-dialogs.js'), 'utf8')}</script>`);
    await page.evaluate(() => document.dispatchEvent(new Event('DOMContentLoaded')));
    const dialog = page.locator('#folder-dialog');
    assert.equal(await dialog.isVisible(), true);
    await page.keyboard.press('Escape');
    await page.mouse.click(5, 5);
    assert.equal(await dialog.isVisible(), true);
  } finally {
    await browser.close();
  }
});
