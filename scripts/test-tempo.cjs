const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');

(async () => {
  const executablePath = process.env.SCORE_TEST_EXECUTABLE;
  const profile = `--user-data-dir=${path.join(root,'diagnostics',executablePath ? 'tempo-packaged-profile' : 'tempo-profile')}`;
  const app = await electron.launch({executablePath,args:executablePath ? [profile] : [root,profile],cwd:root});
  const page = await app.firstWindow();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const state = () => page.evaluate(async () => (await fetch('/api/state', {
    headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}
  })).json());
  try {
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    await page.locator('#notation').selectOption('bass');
    await page.locator('#source').fill(path.join(process.env.APPDATA,'Video Sheet to PDF','output','cache','Pxn4J9DyQZA-av.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#extract').disabled,null,{timeout:120000});
    await page.locator('#advanced').evaluate(element=>element.open=true);
    assert.equal(await page.locator('#timing-repeats').isChecked(),false);
    await page.locator('#detect-tempo').click();
    await page.waitForFunction(()=>!document.querySelector('#tempo-result').hidden,null,{timeout:30000});
    assert.ok(Math.abs(Number(await page.locator('#bpm').inputValue())-113)<1);
    assert.ok((await state()).tempo.consistent);
    await page.locator('#bpm').fill('113');
    assert.equal(await page.locator('#tempo-result').isHidden(),true);
    await page.locator('#timing-repeats').check();
    await page.locator('#extract').click();
    await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden,null,{timeout:300000});
    const result=await state();
    assert.equal(result.error,null);
    assert.equal(result.lines.length,23);
    assert.equal(result.lines[5].time,50.5);
    assert.notEqual(result.lines[4].path,result.lines[5].path);
    assert.ok(result.warnings.some(w=>w.startsWith('Timing inferred 1 repeat(s) after line 5')));
    await page.locator('#preview-print').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open,null,{timeout:60000});
    await page.locator('#print-preview').evaluate(dialog=>dialog.close());
    await page.locator('#capture-tab').click();
    for (const [language,text] of [['ko','오디오에서 BPM 감지'],['ja','音声からBPMを検出'],['en','Detect BPM from audio']]) {
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(text=>document.querySelector('#detect-tempo').textContent===text,text);
    }
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(root,'diagnostics','tempo_review','controls-mobile.png'),fullPage:true});
    // Loading another video must clear the old song's tempo and opt-in.
    await page.locator('#source').fill(path.join(process.env.APPDATA,'Video Sheet to PDF','output','cache','wpme40lu_XE-av.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#extract').disabled,null,{timeout:120000});
    assert.equal(await page.locator('#bpm').inputValue(),'');
    assert.equal(await page.locator('#timing-repeats').isChecked(),false);
    await page.locator('#detect-tempo').click();
    await page.waitForFunction(()=>!document.querySelector('#tempo-result').hidden,null,{timeout:30000});
    assert.equal((await state()).tempo.consistent,false);
    assert.match(await page.locator('#tempo-result').textContent(),/Uncertain/);
    assert.deepEqual(errors,[]);
    console.log('BPM estimation, manual override, SPYAIR 23 lines with repeat at 50.5s, print preview, translations, mobile layout, source reset, and Ado uncertainty passed.');
  } finally { await app.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
