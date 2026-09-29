// Run real packaged extraction using this turn's cached Astra responses.
// Remove CLI discovery from PATH/APPDATA so a cache miss cannot consume quota.
const {_electron:electron}=require('playwright');
const path=require('node:path');
const fs=require('node:fs');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const profile=path.join(root,'diagnostics','ai-cached-profile');
const video=path.join(root,'output','ai-live-e2e','ado-excerpt.mp4');
const identity=crypto.createHash('sha256').update(`${video}:bass`).digest('hex').slice(0,16);
const responses=path.join(profile,'output','ai-jobs',identity,'responses');
fs.mkdirSync(responses,{recursive:true});
const source=path.join(root,'output','ai-optimized-live','responses');
for(const name of fs.readdirSync(source).filter(n=>n.endsWith('.json'))) fs.copyFileSync(path.join(source,name),path.join(responses,name));
(async()=>{
  const app=await electron.launch({executablePath:path.join(root,'dist','win-unpacked','Video Sheet to PDF.exe'),
    args:[`--user-data-dir=${profile}`],cwd:root,
    env:{...process.env,PATH:path.join(process.env.SystemRoot,'System32'),APPDATA:path.join(profile,'empty-appdata')}});
  const page=await app.firstWindow();
  const progress=[];
  await page.route('**/api/state',async route=>{
    const response=await route.fetch();const body=await response.json();
    if(body.busy && body.elapsedSeconds != null) progress.push(body.status);
    await route.fulfill({response,json:body});
  });
  try {
    await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('Choose a video'));
    await page.locator('#ai').click();
    await page.waitForFunction(()=>!document.querySelector('#ai-controls').hidden);
    await page.locator('#notation').selectOption('bass');
    await page.locator('#source').fill(video);
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#ai-extract').disabled);
    await page.locator('#ai-override-bars').click();
    await page.locator('#ai-extract').click();
    await page.waitForFunction(()=>!document.querySelector('#elapsed-time').hidden);
    await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden && document.querySelectorAll('.line-item').length===3,null,{timeout:60000});
    const state=await page.evaluate(async()=>{const r=await fetch('/api/state',{headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}});return r.json();});
    assert.equal(state.error,null);assert.equal(state.aiUsage.requests,0);assert.equal(state.aiUsage.cache_hits,3);
    assert.ok(state.elapsedSeconds>0);
    assert.ok(progress.some(s=>/Preparing|Transcribing|Inspecting|Engraving/.test(s)), 'Actual extraction progress is visible');
    assert.ok(progress.every(s=>!s.startsWith('Video ready')), 'Load status must not survive into extraction');
    const time=await page.locator('#elapsed-time').textContent();
    await page.waitForTimeout(1200);
    assert.equal(await page.locator('#elapsed-time').textContent(),time);
    await page.screenshot({path:path.join(root,'diagnostics','ai-cached-extraction.png')});
    console.log(JSON.stringify({result:'Real packaged extraction passed',cache_hits:state.aiUsage.cache_hits,new_requests:state.aiUsage.requests,elapsed:state.elapsedSeconds,lines:state.lines.length}));
  } catch(error) {console.error(await page.locator('#status').textContent(),await page.locator('#error-text').textContent());throw error;}
  finally{await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
