const {_electron: electron} = require('playwright');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const diagnostics = path.join(root, 'diagnostics');
  fs.mkdirSync(diagnostics, {recursive:true});
  const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const executable = spawnSync(python, ['-c', 'from drumscore.video import ffmpeg_path; print(ffmpeg_path())'], {cwd:root,encoding:'utf8',windowsHide:true});
  assert.equal(executable.status, 0, executable.stderr);
  const videoPath = path.join(diagnostics, 'playback-audio.mp4');
  const silentPath = path.join(diagnostics, 'playback-silent.mp4');
  for (const [destination, sound] of [[videoPath,true],[silentPath,false]]) {
    const inputs = ['-f','lavfi','-i','testsrc2=size=640x360:rate=30'];
    if (sound) inputs.push('-f','lavfi','-i','sine=frequency=440:sample_rate=44100');
    const result = spawnSync(executable.stdout.trim(), ['-y','-hide_banner','-loglevel','error',...inputs,
      '-t','8','-c:v','libx264','-preset','ultrafast','-c:a','aac',destination], {windowsHide:true,encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
  }
  const executablePath = process.env.SCORE_TEST_EXECUTABLE;
  const app = await electron.launch({executablePath,
    args:executablePath ? [`--user-data-dir=${path.join(root,'diagnostics','packaged-playback-profile')}`] : ['-r',path.join(__dirname,'test-profile.cjs'),root],cwd:root,
    env:{...process.env,VIDEO_SHEET_TEST_PROFILE:'playback'}});
  try {
    const page = await app.firstWindow();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.setViewportSize({width:1280,height:700});
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Choose a video'));
    await page.locator('#source').fill(videoPath);
    await page.locator('#load-video').click();
    await page.waitForFunction(() => !document.querySelector('#play').disabled);
    assert.equal(await page.locator('#mode-hint, #show-frame, #add-view').count(),0);
    assert.equal(await page.locator('#audio-note').isVisible(),false);
    const sidebar = await page.locator('.capture-sidebar').boundingBox();
    const stage = await page.locator('.video-workspace').boundingBox();
    assert.ok(sidebar.x >= stage.x+stage.width);
    // Analyse decoded audio while keeping the test silent at the speakers.
    await page.evaluate(() => {
      const video = document.querySelector('video');
      const context = new AudioContext();
      const source = context.createMediaElementSource(video);
      const analyser = context.createAnalyser();
      const silence = context.createGain(); silence.gain.value = 0;
      source.connect(analyser); analyser.connect(silence); silence.connect(context.destination);
      window.audioTest = {context,analyser};
    });
    await page.locator('#play').click();
    await page.evaluate(() => window.audioTest.context.resume());
    await page.waitForFunction(() => {
      const data = new Float32Array(window.audioTest.analyser.fftSize);
      window.audioTest.analyser.getFloatTimeDomainData(data);
      return data.some(sample => Math.abs(sample) > .001);
    });
    assert.equal(await page.locator('video').evaluate(v => v.muted),false);
    await page.locator('#mute').click();
    assert.equal(await page.locator('video').evaluate(v => v.muted),true);
    await page.locator('#mute').click();
    await page.locator('#volume').fill('25');
    assert.equal(await page.locator('video').evaluate(v => v.volume),.25);
    await page.locator('#advanced').evaluate(node => node.open = true);
    const widths = async () => page.evaluate(() => ['.capture-sidebar','#source','.segmented'].map(selector => document.querySelector(selector).getBoundingClientRect().width));
    const automaticWidths = await widths();
    await page.locator('#manual').click();
    await page.waitForFunction(() => !document.querySelector('#manual-controls').hidden && !document.querySelector('#play').disabled);
    assert.deepEqual(await widths(),automaticWidths);
    assert.equal(await page.locator('video').evaluate(v => v.paused),true);
    await page.locator('#seek').fill('2.5');
    await page.waitForFunction(() => !document.querySelector('video').seeking);
    assert.ok(Math.abs(await page.locator('video').evaluate(v => v.currentTime)-2.5)<.1);
    await page.locator('#speed').selectOption('1.5');
    assert.equal(await page.locator('video').evaluate(v => v.playbackRate),1.5);
    for (const speed of ['2.5','3']) {
      await page.locator('#speed').selectOption(speed);
      assert.equal(await page.locator('video').evaluate(v => v.playbackRate),Number(speed));
      assert.equal(await page.locator('#review-speed').inputValue(),speed);
    }
    await page.locator('#speed').selectOption('1');
    await page.locator('#play').click();
    await page.waitForFunction(() => !document.querySelector('video').paused);
    await page.locator('#add-line').click();
    await page.waitForFunction(() => document.querySelector('#manual-count').textContent === '1');
    await page.screenshot({path:path.join(diagnostics,'audio-layout-manual.png')});
    await page.locator('#review-tab').click();
    assert.equal(await page.locator('video').evaluate(v => v.paused),true);
    assert.equal(await page.locator('#review-audio').isChecked(),false);
    assert.equal(await page.locator('#review-play').isDisabled(),true);
    await page.locator('#review-audio').check();
    await page.waitForFunction(() => !document.querySelector('video').paused);
    const reviewTime = await page.locator('video').evaluate(v => v.currentTime);
    await page.waitForFunction(time => document.querySelector('video').currentTime > time + .15, reviewTime);
    await page.locator('#review-speed').selectOption('3');
    assert.equal(await page.locator('video').evaluate(v => v.playbackRate),3);
    assert.equal(await page.locator('#speed').inputValue(),'3');
    await page.locator('#review-play').click();
    assert.equal(await page.locator('video').evaluate(v => v.paused),true);
    await page.locator('#review-speed').selectOption('1');
    await page.locator('#capture-tab').click();
    assert.equal(await page.locator('#keep-review-audio').isChecked(),true);
    await page.locator('#seek').fill('0');
    await page.waitForFunction(() => !document.querySelector('#play').disabled);
    await page.locator('#play').click();
    await page.locator('#review-tab').click();
    assert.equal(await page.locator('video').evaluate(v => v.paused),false);
    await page.locator('#review-audio').uncheck();
    assert.equal(await page.locator('video').evaluate(v => v.paused),true);
    await page.locator('#capture-tab').click();
    for (const count of ['2','3']) {
      await page.locator('#add-line').click();
      await page.waitForFunction(value => document.querySelector('#manual-count').textContent === value, count);
    }
    await page.locator('#review-tab').click();
    await page.locator('.line-item').first().click();
    const assertLine = async number => assert.equal(await page.locator('#preview-title').textContent(), `Line 0${number}`);
    await page.keyboard.press('ArrowDown'); await assertLine(2);
    await page.keyboard.press('ArrowRight'); await assertLine(3);
    await page.keyboard.press('ArrowDown'); await assertLine(3);
    await page.keyboard.press('ArrowUp'); await assertLine(2);
    await page.keyboard.press('ArrowLeft'); await assertLine(1);
    await page.keyboard.press('ArrowUp'); await assertLine(1);
    assert.equal(await page.locator('.line-item').first().evaluate(el => el === document.activeElement),true);
    await page.locator('#pdf-title').focus();
    await page.keyboard.press('ArrowRight'); await assertLine(1);
    await page.locator('#gap').fill('1.5');
    await page.keyboard.press('ArrowUp'); await assertLine(1);
    assert.equal(await page.locator('#gap').inputValue(),'2');
    await page.locator('#edit-line').click();
    await page.locator('#close-editor').focus();
    await page.keyboard.press('ArrowDown'); await assertLine(1);
    await page.locator('#close-editor').click();
    await page.screenshot({path:path.join(diagnostics,'review-audio-keyboard.png')});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth));
    await page.locator('#review-audio').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(diagnostics,'review-audio-mobile.png')});
    await page.setViewportSize({width:1280,height:700});
    await page.locator('#capture-tab').click();
    await page.locator('#automatic').click();
    await page.waitForFunction(() => document.querySelector('#automatic').getAttribute('aria-pressed') === 'true');
    assert.deepEqual(await widths(),automaticWidths);
    await page.screenshot({path:path.join(diagnostics,'audio-layout-automatic.png')});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth));
    await page.locator('#mute').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(diagnostics,'audio-layout-mobile.png')});
    await page.locator('#source').fill(silentPath);
    await page.locator('#load-video').click();
    await page.waitForFunction(() => !document.querySelector('#audio-note').hidden && !document.querySelector('#play').disabled);
    assert.equal(await page.locator('#mute').isDisabled(),true);
    assert.equal(await page.locator('#keep-review-audio').isDisabled(),true);
    assert.deepEqual(errors,[]);
    console.log('Passed: decoded audio, mute, volume, speeds through 3x, opt-in review playback, arrow selection and input guards, both modes, fixed widths, seeking, capture, silent source, mobile layout.');
  } finally { await app.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
