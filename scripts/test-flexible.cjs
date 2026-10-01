const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'..');

(async () => {
  const executablePath = process.env.SCORE_TEST_EXECUTABLE;
  const profile = `--user-data-dir=${path.join(root,'diagnostics','flexible-ui-profile')}`;
  const app = await electron.launch({executablePath,args:executablePath ? [profile] : [root,profile],cwd:root});
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror',e=>errors.push(e.message));
  const state = () => page.evaluate(async () => (await fetch('/api/state',{
    headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}
  })).json());
  try {
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    await page.locator('#advanced').evaluate(e=>e.open=true);
    for (const notation of ['staff','piano','bass','guitar']) {
      await page.locator('#notation').selectOption(notation);
      assert.ok(await page.locator('#bpm').isVisible());
      assert.ok(await page.locator('#flexible-area').isVisible());
    }
    // Chords & lyrics is an instrument now; timing and follow controls do not apply to it.
    await page.locator('#notation').selectOption('chord');
    await page.waitForFunction(()=>document.querySelector('#timing-controls').hidden);
    assert.ok(await page.locator('#bpm').isHidden());
    assert.ok(await page.locator('#flexible-area').isHidden());
    await page.locator('#notation').selectOption('bass');
    await page.waitForFunction(()=>!document.querySelector('#timing-controls').hidden);
    await page.locator('#source').fill(path.join(process.env.APPDATA,'Video Sheet to PDF/output/cache/f5VnaleBDJM-av.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#extract').disabled,null,{timeout:120000});
    assert.equal(await page.locator('#flexible-area').isChecked(),false);
    assert.equal(await page.locator('#timing-repeats').isChecked(),false);
    await page.locator('#advanced').evaluate(e=>e.open=true);
    await page.locator('#start').fill('176');
    await page.locator('#end').fill('204');
    await page.locator('#flexible-area').check();
    await page.locator('#bpm').fill('145');
    await page.locator('#timing-repeats').check();
    await page.locator('#extract').click();
    await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden,null,{timeout:180000});
    const result = await state();
    assert.equal(result.error,null);
    assert.equal(result.lines.length,4);
    assert.ok(result.lines.some(l=>Math.abs(l.time-183)<1));
    assert.ok(result.lines.some(l=>Math.abs(l.time-189.5)<1));
    assert.ok(result.warnings.some(w=>w.includes('added 0 inferred line(s)')));
    await page.locator('#capture-tab').click();
    for (const [language,text] of [['ko','악보 위치 변화 따라가기'],['ja','楽譜の位置変化を追跡'],['en','Follow changing score position']]) {
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(text=>document.querySelector('#flexible-area').parentElement.textContent===text,text);
    }
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    console.log('All-instrument BPM controls, Chord visibility, opt-in defaults, flexible extraction, missing line, rest grouping, timing completion, translations and mobile layout passed.');
  } finally { await app.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
