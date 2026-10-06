// Real Automatic capture of the supplied scrolling drum video, without AI calls.
const {_electron: electron} = require('playwright');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const profile = path.join(root, 'diagnostics', 'drum-scroll-profile');
  fs.mkdirSync(profile, {recursive:true});
  const executablePath = process.env.SCORE_TEST_EXECUTABLE || path.join(root, 'dist', 'win-unpacked', 'Video Sheet to PDF.exe');
  const app = await electron.launch({executablePath, args:[`--user-data-dir=${profile}`], cwd:root});
  const page = await app.firstWindow();
  try {
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('Choose a video'));
    await page.locator('#automatic').click();
    await page.locator('#notation').selectOption('staff');
    await page.locator('#source').fill(path.join(root, 'diagnostics', 'drum-scroll', 'cache', 'PivrPuH1NrA-av.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(() => !document.querySelector('#extract').disabled);
    await page.locator('#advanced').evaluate(node => node.open = true);
    await page.locator('#end').fill('45');
    await page.locator('#extract').click();
    await page.waitForFunction(() => !document.querySelector('#review-screen').hidden, null, {timeout:180000});
    const state = await page.evaluate(async () => {
      const response = await fetch('/api/state', {headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}});
      return response.json();
    });
    assert.equal(state.error, null);
    assert.equal(state.lines.length, 8, 'Overlapping pages should yield eight complete rows in the first 45 seconds');
    assert.equal(state.mode, 'automatic');
    assert.ok(state.elapsedSeconds > 0);
    await page.screenshot({path:path.join(root, 'diagnostics', 'drum-scroll', 'packaged-review.png')});
    console.log(JSON.stringify({result:'Packaged scrolling drum capture passed',lines:state.lines.length,elapsed:state.elapsedSeconds}));
  } catch (error) {
    console.error(await page.locator('#status').textContent());
    throw error;
  } finally {
    await app.close();
  }
})().catch(error => {console.error(error); process.exitCode=1;});
