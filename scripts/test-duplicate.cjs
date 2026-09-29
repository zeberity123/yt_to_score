const {_electron: electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');

(async () => {
  const executablePath = process.env.SCORE_TEST_EXECUTABLE;
  const args = [`--user-data-dir=${path.join(root,'diagnostics',executablePath ? 'duplicate-packaged-profile' : 'duplicate-profile')}`];
  const app = await electron.launch({executablePath,args:executablePath ? args : [root,...args],cwd:root});
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = () => page.evaluate(async () => (await fetch('/api/state', {
    headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}
  })).json());
  try {
    await page.waitForFunction(() => !document.querySelector('#open-project').disabled);
    assert.equal(await page.locator('#duplicate-line').isDisabled(), true);
    await app.evaluate(({dialog}, filename) => {
      dialog.showOpenDialog = async () => ({canceled:false,filePaths:[filename]});
    }, path.join(root,'screen_sample','spyair_test1.drumscore'));
    await page.locator('#open-project').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 22);
    await page.locator('.line-item').nth(4).click();
    const original = (await state()).lines[4];
    await page.locator('#duplicate-line').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 23);
    let result = await state();
    assert.equal(result.lines[5].time, original.time);
    assert.notEqual(result.lines[5].path, original.path);
    await page.locator('#edit-line').click();
    await page.waitForFunction(() => document.querySelector('#editor-image').naturalWidth > 0);
    await page.locator('#line-height').fill('75');
    await page.locator('#apply-edit').click();
    await page.waitForFunction(() => !document.querySelector('#editor').open);
    result = await state();
    assert.equal(result.lines[5].height_scale, .75);
    assert.equal(result.lines[4].height_scale, 1);
    await page.locator('#include-line').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 22);
    await page.locator('#undo-line').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 23);
    await page.locator('.line-item').last().click();
    await page.locator('#duplicate-line').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 24);
    assert.equal(await page.locator('.line-item').last().getAttribute('aria-pressed'), 'true');
    for (const [language, label] of [['ko','복제'],['ja','複製'],['en','Duplicate']]) {
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(text => document.querySelector('#duplicate-line').textContent === text, label);
    }
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:path.join(root,'diagnostics','bass_review','duplicate-mobile.png')});
    assert.deepEqual(errors, []);
    console.log('Duplicate: insert, independent edit, remove/undo, translations, and mobile layout passed.');
  } finally {
    await app.close();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
