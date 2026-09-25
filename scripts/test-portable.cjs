const {chromium} = require('playwright');
const {spawn, spawnSync} = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const version = require('../package.json').version;
  const executable = path.join(root, 'dist', `Video-Sheet-to-PDF-${version}-win-x64.exe`);
  const profile = path.join(root, 'diagnostics', 'portable-test-profile');
  const ffmpegFolder = path.join(root, 'dist/win-unpacked/resources/backend/_internal/imageio_ffmpeg/binaries');
  const ffmpeg = path.join(ffmpegFolder, fs.readdirSync(ffmpegFolder).find(name => name.endsWith('.exe')));
  const source = path.join(root, 'diagnostics', 'portable-conversion.mkv');
  const generated = spawnSync(ffmpeg, ['-y','-hide_banner','-loglevel','error',
    '-f','lavfi','-i','testsrc2=size=640x360:rate=24','-f','lavfi','-i','sine=frequency=440',
    '-t','8','-c:v','mpeg4','-c:a','pcm_s16le',source], {encoding:'utf8',windowsHide:true});
  assert.equal(generated.status,0,generated.stderr);
  const server = net.createServer();
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const env = {...process.env};
  for (const key of Object.keys(env)) if (['path','pythonpath','pythonhome','imageio_ffmpeg_exe','drumscore_node','drumscore_output'].includes(key.toLowerCase())) delete env[key];
  env.PATH = path.join(process.env.SystemRoot, 'System32');
  const child = spawn(executable, [`--user-data-dir=${profile}`,`--remote-debugging-port=${port}`],
    {cwd:path.dirname(executable),env,windowsHide:true,stdio:'ignore'});
  let browser;
  try {
    const endpoint = `http://127.0.0.1:${port}`;
    const deadline = Date.now()+120000;
    while (Date.now()<deadline) {
      try { if ((await fetch(`${endpoint}/json/version`)).ok) break; } catch {}
      if (child.exitCode !== null) throw new Error(`Portable launcher exited: ${child.exitCode}`);
      await new Promise(resolve => setTimeout(resolve,500));
    }
    browser = await chromium.connectOverCDP(endpoint);
    const context = browser.contexts()[0];
    const page = context.pages()[0] || await context.waitForEvent('page');
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('Choose a video'));
    await page.locator('#source').fill(source);
    await page.locator('#load-video').click();
    await page.waitForFunction(() => !document.querySelector('#play').disabled, null, {timeout:60000});
    assert.equal(await page.locator('#audio-note').isVisible(),false);
    await page.locator('#manual').click();
    await page.waitForFunction(() => !document.querySelector('#add-line').disabled);
    await page.locator('#add-line').click();
    await page.waitForFunction(() => document.querySelector('#manual-count').textContent === '1');
    await page.locator('#review-tab').click();
    assert.equal(await page.locator('#gap').inputValue(),'0');
    assert.equal(await page.locator('#left-margin').inputValue(),'3');
    assert.equal(await page.locator('#right-margin').inputValue(),'3');
    await page.locator('#for-print').click();
    assert.equal(await page.locator('#gap').inputValue(),'0');
    assert.equal(await page.locator('#left-margin').inputValue(),'12');
    assert.equal(await page.locator('#right-margin').inputValue(),'12');
    await page.screenshot({path:path.join(root,'diagnostics','portable-release.png')});
    assert.equal(await page.locator('#error').isVisible(),false);
    assert.ok(fs.readdirSync(path.join(profile,'output')).some(name => name.startsWith('manual_')));
    const session = await browser.newBrowserCDPSession();
    console.log('Passed: single EXE launch, isolated persistent data, video/audio conversion and capture without system Python/Node/FFmpeg, defaults and print preset.');
    const exited = new Promise(resolve => child.once('exit',resolve));
    session.send('Browser.close').catch(() => {});
    await Promise.race([exited,new Promise(resolve => setTimeout(resolve,5000))]);
    browser = null;
  } finally {
    if (browser) {
      try { const session = await browser.newBrowserCDPSession(); await session.send('Browser.close'); } catch {}
    }
    if (child.exitCode === null) {
      await Promise.race([new Promise(resolve => child.once('exit',resolve)), new Promise(resolve => setTimeout(resolve,10000))]);
      if (child.exitCode === null) spawnSync('taskkill',['/pid',String(child.pid),'/t','/f'],{windowsHide:true,stdio:'ignore'});
    }
  }
})().catch(error => {console.error(error);process.exitCode=1;});
