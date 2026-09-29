const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');

(async () => {
  const executablePath = process.env.SCORE_TEST_EXECUTABLE;
  assert.ok(executablePath, 'Set SCORE_TEST_EXECUTABLE to the packaged application.');
  const app = await electron.launch({executablePath,
    args:[`--user-data-dir=${path.join(root,'diagnostics','bass-release-profile')}`],cwd:root});
  const page = await app.firstWindow();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const state = () => page.evaluate(async () => (await fetch('/api/state', {
    headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}
  })).json());
  try {
    await page.waitForFunction(()=>!document.querySelector('#load-video').disabled || !document.querySelector('#open-project').disabled);
    await page.locator('#notation').selectOption('bass');
    const video=path.join(process.env.APPDATA,'Video Sheet to PDF','output','cache','wpme40lu_XE-av.mp4');
    await page.locator('#source').fill(video);
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#extract').disabled,null,{timeout:120000});
    // Explicit detection at a score-bearing frame avoids the opening fade.
    await page.locator('video').evaluate(video=>video.currentTime=20);
    await page.waitForFunction(()=>!document.querySelector('#detect').disabled);
    await page.locator('#detect').click();
    await page.waitForFunction(()=>!document.querySelector('#detect').disabled);
    const crop=(await state()).region;
    assert.ok(crop.top>.65 && crop.top<.72 && crop.bottom<.93);
    await page.locator('#advanced').evaluate(element=>element.open=true);
    await page.locator('#end').fill('45');
    await page.locator('#extract').click();
    await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden,null,{timeout:180000});
    const result=await state();
    assert.equal(result.error,null);
    assert.ok(result.lines.length>=5);
    assert.ok(result.lines.filter(line=>line.bar_bounds && line.bar_numbers).length>=5);
    assert.ok(result.lines.every(line=>line.raw_source_path));
    assert.ok(result.warnings.some(warning=>warning.startsWith('Recovered ')),JSON.stringify(result.warnings));
    await page.locator('#preview-print').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open,null,{timeout:60000});
    assert.ok((await state()).printPreview.widths.length>0);
    await page.screenshot({path:path.join(root,'diagnostics','bass_review','packaged-recovery.png')});
    assert.deepEqual(errors,[]);
    console.log('Packaged bass recovery: crop, numbered-bar extraction, review warnings, and print preview passed.');
    console.log(result.warnings.join('\n'));
  } finally {
    await app.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
