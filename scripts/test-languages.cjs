const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'..');
const profile = path.join(root,'diagnostics','languages-profile');
async function launch() {
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const app = await electron.launch({executablePath,args:executablePath?[`--user-data-dir=${profile}`]:[root,`--user-data-dir=${profile}`],cwd:root});
  const page = await app.firstWindow();
  await page.waitForFunction(() => !document.querySelector('#open-project').disabled);
  return {app,page};
}
(async () => {
  let {app,page} = await launch();
  const errors=[];
  page.on('pageerror', error => errors.push(error.message));
  try {
    for (const [language,open,status] of [['ko','프로젝트 열기','악보로 만들 동영상을 선택하세요.'],['ja','プロジェクトを開く','楽譜にする動画を選択してください。'],['en','Open project','Choose a video to start your score.']]) {
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(value => document.querySelector('#status').textContent === value,status);
      assert.ok((await page.locator('#open-project').textContent()).includes(open));
      assert.equal(await page.locator('html').getAttribute('lang'), language);
      const a = await page.locator('#language').boundingBox(), b = await page.locator('#open-project').boundingBox();
      assert.ok(a.x+a.width <= b.x);
      for (const width of [390,820,1440]) {
        await page.setViewportSize({width,height:900});
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),`${language} at ${width}`);
      }
    }
    await page.locator('#language').selectOption('ko');
    await page.locator('#source').fill(path.join(root,'samples','kgNjaXTh0rU.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(() => !document.querySelector('#add-line').disabled, null,{timeout:60000});
    await page.locator('#manual').click();
    await page.locator('#add-line').click();
    await page.locator('#review-tab').click();
    await page.waitForFunction(() => document.querySelector('#preview-title').textContent === '악보 줄 01');
    await page.locator('#pdf-title').fill('기타 楽譜 My title');
    await page.locator('#edit-line').click();
    await page.locator('#language').evaluate(node => {node.value='ja';node.dispatchEvent(new Event('change'));});
    await page.waitForFunction(() => document.querySelector('#editor-title').textContent === '段 01 を編集');
    assert.equal(await page.locator('#pdf-title').inputValue(),'기타 楽譜 My title');
    await page.locator('#cancel-edit').click();
    await page.locator('#include-line').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('段を削除しました'));
    await page.locator('#undo-line').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent === '段を復元しました。');
    await page.screenshot({path:path.join(root,'diagnostics','japanese-review.png')});
    // Wait for persistence, independent of the ephemeral backend port.
    await page.waitForFunction(async () => (await window.desktop.getLanguage()) === 'ja');
    assert.deepEqual(errors,[]);
  } finally {await app.close();}
  ({app,page} = await launch());
  try {
    assert.equal(await page.locator('#language').inputValue(),'ja');
    assert.ok((await page.locator('#open-project').textContent()).includes('プロジェクトを開く'));
    await page.locator('#language').selectOption('en');
  } finally {await app.close();}
  console.log('Passed: English/Korean/Japanese, dynamic text, crop dialog, title preservation, mobile layout and restart persistence.');
})().catch(error => {console.error(error);process.exitCode=1;});
