const {_electron: electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');

(async () => {
  fs.mkdirSync(path.join(root, 'diagnostics'), {recursive:true});
  execFileSync(path.join(root, '.venv/Scripts/python.exe'), ['-c',
    "import runpy; from pathlib import Path; t=runpy.run_path('tests/test_free.py'); t['video'](Path('diagnostics/free-fixture.avi'), [['Am7 G /', 'First lyric', 'Dm7 E7 /', 'Next lyric'], ['Am7']])"], {cwd:root});
  const executablePath = process.env.SCORE_TEST_EXECUTABLE;
  const profile = `--user-data-dir=${path.join(root, 'diagnostics', executablePath ? 'free-packaged-profile' : 'free-ui-profile')}`;
  const app = await electron.launch({executablePath, args:executablePath ? [profile] : [root, profile], cwd:root});
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.waitForFunction(() => !document.querySelector('#free').disabled);
    await page.locator('#language').selectOption('en');
    await page.locator('#free').click();
    await page.waitForFunction(() => document.querySelector('#free').getAttribute('aria-pressed') === 'true');
    assert.equal(await page.locator('#free').getAttribute('aria-pressed'), 'true');
    assert.equal(await page.locator('#notation-controls').isVisible(), false);
    assert.equal(await page.locator('#extract').textContent(), 'Extract text lines →');
    await page.locator('#source').fill(path.join(root, 'diagnostics/free-fixture.avi'));
    await page.locator('#load-video').click();
    await page.waitForFunction(() => !document.querySelector('#play').disabled, null, {timeout:60000});
    await page.locator('#advanced').evaluate(element => element.open = true);
    await page.locator('#start').fill('0');
    await page.locator('#end').fill('4');
    await page.locator('#extract').click();
    await page.waitForFunction(() => !document.querySelector('#review-screen').hidden, null, {timeout:60000});
    assert.equal(await page.locator('.line-item').count(), 5);
    assert.equal(await page.locator('#background').inputValue(), 'white');
    for (const background of ['black','original','white']) {
      await page.locator('#background').selectOption(background);
      await page.waitForFunction(background => {
        const img=document.querySelector('#line-image');
        if (!img.complete || !img.naturalWidth || !img.dataset.key.includes(`:${background}:`)) return false;
        const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
        const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
        const pixel=ctx.getImageData(canvas.width-10,Math.floor(canvas.height/2),1,1).data;
        return background==='white' ? pixel[0]===255 && pixel[1]===255 : background==='black' ? pixel[0]===0 && pixel[1]===0 : pixel[0]>100 && pixel[0]<250;
      },background);
    }
    await page.locator('#edit-line').click();
    await page.waitForFunction(() => document.querySelector('#editor-image').naturalWidth === 960);
    await page.locator('#cancel-edit').click();
    await page.locator('#include-line').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 4);
    assert.equal(await page.locator('.line-item').count(), 4);
    await page.locator('#undo-line').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 5);
    assert.equal(await page.locator('.line-item').count(), 5);
    await page.locator('#capture-tab').click();
    const settings=page.locator('#advanced>summary');
    assert.equal(await settings.getAttribute('role'),'button');
    assert.ok(await settings.locator('svg').isVisible());
    await settings.click();
    await page.waitForFunction(() => document.querySelector('#advanced>summary').getAttribute('aria-expanded') === 'false');
    await settings.click();
    await page.waitForFunction(() => document.querySelector('#advanced>summary').getAttribute('aria-expanded') === 'true');
    await page.locator('#manual').click();
    await page.waitForFunction(() => document.querySelector('#manual').getAttribute('aria-pressed') === 'true');
    assert.equal(await page.locator('.line-item').count(), 0);
    await page.locator('#automatic').click();
    await page.waitForFunction(() => document.querySelector('#automatic').getAttribute('aria-pressed') === 'true');
    assert.equal(await page.locator('#notation-controls').isVisible(), true);
    await page.locator('#free').click();
    await page.waitForFunction(() => document.querySelectorAll('.line-item').length === 5);
    assert.equal(await page.locator('.line-item').count(), 5);
    for (const [language,label,extract] of [['ko','코드/가사','텍스트 줄 추출'],['ja','コード/歌詞','テキスト行を抽出'],['en','Chord','Extract text lines']]) {
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(label => document.querySelector('#free').textContent === label, label);
      await page.waitForFunction(label => document.querySelector('#extract').textContent.includes(label), extract);
    }
    for (const width of [1280,390]) {
      await page.setViewportSize({width,height:844});
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const boxes = await Promise.all(['automatic','manual','free'].map(id => page.locator(`#${id}`).boundingBox()));
      assert.ok(boxes.every(box => box && box.width > 40));
    }
    await page.screenshot({path:path.join(root,'diagnostics/free-mobile.png')});
    await page.setViewportSize({width:1280,height:900});
    await page.screenshot({path:path.join(root,'diagnostics/chord-settings.png')});
    const tuki=path.join(root,'screen_sample/tuki_test1.drumscore');
    if (fs.existsSync(tuki)) {
      await app.evaluate(({dialog},filename)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[filename]});},tuki);
      await page.locator('#open-project').click();
      await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===29);
      await page.locator('#bars-per-line').fill('4');
      await page.locator('#bars-per-line').press('Tab');
      await page.waitForFunction(()=>!document.querySelector('#background').disabled);
      await page.locator('#background').selectOption('black');
      await page.waitForFunction(()=>!document.querySelector('#preview-print').disabled);
      await page.locator('#preview-print').click();
      await page.waitForFunction(()=>document.querySelector('#print-preview').open);
      assert.equal(await page.locator('#print-preview-notes').textContent(),'');
      assert.equal(await page.locator('#print-preview-rows img').count(),15);
      await page.waitForFunction(()=>{const img=document.querySelector('#print-preview-rows img');return img.complete&&img.naturalWidth;});
      await page.screenshot({path:path.join(root,'diagnostics/tuki-black-preview.png')});
      await page.locator('#close-print-preview').click();
    }
    assert.deepEqual(errors, []);
    console.log('Passed Chord extraction, background switching, settings button, editing, translations, mobile layout and available tuki reflow.');
  } catch (error) {
    console.error(await page.evaluate(async()=>({status:document.querySelector('#status').textContent,error:document.querySelector('#error-text').textContent,
      state:await(await fetch('/api/state',{headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}})).json()})));
    await page.screenshot({path:path.join(root,'diagnostics/chord-test-failure.png')});
    throw error;
  } finally {
    await app.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
