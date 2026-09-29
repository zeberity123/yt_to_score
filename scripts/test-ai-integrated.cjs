const {_electron: electron} = require('playwright');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname,'..');
const folder = path.join(root,'diagnostics','ai-integrated');
fs.mkdirSync(folder,{recursive:true});
const fixture = path.join(folder,'fixture.aiscore.json');
const title = `Integrated AI test ${Date.now()}`;
const example = JSON.parse(fs.readFileSync(path.join(root,'independent_score','ai_example','Ado.aiscore.json'),'utf8'));
example.bars=example.bars.slice(0,10);
example.bars.forEach(b=>b.system_end=[3,7,10].includes(b.number));
example.meta.last_bar=10;example.meta.source_bars_per_line=0;
example.layout.bars_per_line=0;example.layout.merge_rests=[];example.layout.song_info='';
fs.writeFileSync(fixture,JSON.stringify(example));
(async()=>{
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const app=await electron.launch({executablePath,
    args:executablePath?[`--user-data-dir=${path.join(folder,'profile')}`]:['-r',path.join(__dirname,'test-profile.cjs'),root],
    cwd:root,env:{...process.env,DRUMSCORE_OUTPUT:path.join(folder,'workspace'),ELECTRON_DISABLE_SECURITY_WARNINGS:'true'}});
  const page=await app.firstWindow();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const idle=()=>page.waitForFunction(()=>!document.querySelector('#load-video').disabled && document.querySelector('#cancel').hidden);
  try {
    await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('Choose a video'));
    assert.equal(await page.locator('#automatic').textContent(),'Automatic');
    assert.equal(await page.locator('#ai').textContent(),'AI');
    assert.equal(await page.locator('#free').count(),0);
    assert.equal(await page.locator('#auto-controls').isVisible(),true);
    assert.equal(await page.locator('#ai-controls').isVisible(),false);
    await page.locator('#ai').click();
    await page.waitForFunction(()=>!document.querySelector('#ai-controls').hidden && document.querySelector('#auto-controls').hidden);
    // Keeping video images is the default: no bars-per-line or instructions, capture settings move under AI.
    assert.equal(await page.locator('#ai-method').inputValue(),'images');
    assert.equal(await page.locator('#ai-bars-control').isVisible(),false);
    assert.equal(await page.locator('#ai-instructions-step').isVisible(),false);
    assert.equal(await page.locator('#ai-capture-settings #advanced').count(),1);
    await page.locator('#ai-method').selectOption('notation');
    await page.waitForFunction(()=>!document.querySelector('#ai-bars-control').hidden && document.querySelector('#auto-capture-settings #advanced'));
    assert.equal(await page.locator('#ai-override-bars').getAttribute('aria-pressed'),'false');
    assert.equal(await page.locator('#ai-override-bars').textContent(),'Override bars per line: OFF');
    assert.equal(await page.title(),'Video Sheet to PDF');
    assert.equal(await page.locator('#ai-bars').isDisabled(),true);
    assert.equal(await page.locator('#ai-model').inputValue(),'gpt-6-astra');
    await page.locator('#ai-provider').selectOption('OpenAI');
    assert.equal(await page.locator('#ai-model').inputValue(),'gpt-6-luna');
    assert.equal(await page.locator('#ai-key').isVisible(),true);
    await page.locator('#ai-key').fill('test-key-not-saved');
    await page.locator('#ai-provider').selectOption('Claude CLI');
    assert.equal(await page.locator('#ai-key').inputValue(),'');
    assert.equal(await page.locator('#ai-key-field').isHidden(),true);
    await page.locator('#notation').selectOption('chord');
    assert.equal(await page.locator('#ai-override-bars').isDisabled(),true);
    await page.locator('#notation').selectOption('bass');
    await page.locator('#ai-provider').selectOption('Codex');
    assert.equal(await page.locator('#ai-instructions').inputValue(),'');
    assert.equal(await page.locator('#ai-instructions').getAttribute('placeholder'),null);
    assert.equal(await page.locator('.ai-limits,#ai-budget,#ai-requests').count(),0);
    assert.equal(await page.locator('[aria-label="Playback"] .step-dot').count(),0);
    await page.locator('#source').fill(path.join(root,'output/ai-live-e2e/ado-excerpt.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#ai-extract').disabled && !document.querySelector('#play').disabled);
    assert.ok((await page.locator('#status').textContent()).includes('Choose Extract with AI'));
    await page.locator('video').evaluate(v=>{v.currentTime=5;});
    await page.waitForFunction(()=>!document.querySelector('video').seeking);
    await page.locator('#manual').click();
    await page.waitForFunction(()=>!document.querySelector('#manual-controls').hidden && !document.querySelector('#play').disabled);
    assert.ok(Math.abs(await page.locator('video').evaluate(v=>v.currentTime)-5)<.1, 'Manual keeps current time');
    await page.locator('#automatic').click();
    await page.waitForFunction(()=>!document.querySelector('#auto-controls').hidden && !document.querySelector('#extract').disabled && !document.querySelector('#video-crop').hidden);
    await page.locator('#ai').click();
    await page.waitForFunction(()=>!document.querySelector('#ai-controls').hidden && document.querySelector('#video-crop').hidden);
    await page.locator('#ai-select-area').check();
    const area=await page.locator('#video-crop').boundingBox();
    await page.mouse.move(area.x+area.width*.05,area.y+area.height*.6);
    await page.mouse.down();await page.mouse.move(area.x+area.width*.95,area.y+area.height*.95,{steps:5});await page.mouse.up();
    await page.waitForFunction(()=>!document.querySelector('#ai-extract').disabled);
    if(process.env.SCORE_TEST_CODEX_LOGIN==='1') {
      await page.locator('#ai-check').click();
      await page.waitForFunction(()=>document.querySelector('#ai-connection-note').textContent.includes('Signed in with ChatGPT') && document.querySelector('#cancel').hidden);
    }
    // Check the user's exact failure: blank instructions/default controls must
    // dispatch extraction. Stop at the transport boundary so tests spend no quota.
    const extractionRequests=[];
    await page.route('**/api/command',async route=>{
      const data=route.request().postDataJSON();
      if(data.action==='ai-extract') {
        extractionRequests.push(data);
        await route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Extraction dispatch verified (test only).'})});
      } else await route.continue();
    });
    for(const provider of ['Codex','Claude CLI','OpenAI','DeepSeek','Anthropic']) {
      await page.locator('#ai-provider').selectOption(provider);
      if(!['Codex','Claude CLI'].includes(provider)) await page.locator('#ai-key').fill('test-only-no-request');
      await page.locator('#ai-extract').click();
      await page.waitForFunction(()=>!document.querySelector('#error').hidden);
      assert.equal(extractionRequests.at(-1)?.provider,provider);
      assert.equal(extractionRequests.at(-1)?.method,'notation');
      assert.equal(extractionRequests.at(-1)?.instructions,'');
      assert.equal(extractionRequests.at(-1)?.bars,0);
      assert.ok(extractionRequests.at(-1)?.crop[1] > .55);
      assert.equal('budget' in extractionRequests.at(-1),false);
      await page.locator('#dismiss-error').click();
    }
    assert.equal(extractionRequests.length,5);
    await page.locator('#ai-method').selectOption('images');
    await page.locator('#ai-extract').click();
    await page.waitForFunction(()=>!document.querySelector('#error').hidden);
    assert.equal(extractionRequests.at(-1)?.method,'images');
    assert.equal(extractionRequests.at(-1)?.interval,'0.5');
    await page.locator('#dismiss-error').click();
    await page.locator('#ai-method').selectOption('notation');
    await page.waitForFunction(()=>!document.querySelector('#ai-bars-control').hidden);
    await page.locator('#ai-select-area').uncheck();
    assert.equal(await page.locator('#video-crop').isHidden(),true);
    await page.mouse.move(10,10);
    const toggleColor = await page.locator('#ai-override-bars').evaluate(e=>getComputedStyle(e).backgroundColor);
    await page.locator('#ai-override-bars').click();
    await page.mouse.move(10,10);
    await page.waitForTimeout(200);
    assert.equal(await page.locator('#ai-override-bars').textContent(),'Override bars per line: ON');
    assert.equal(await page.locator('#ai-override-bars').evaluate(e=>getComputedStyle(e).backgroundColor),toggleColor);
    assert.equal(await page.locator('#ai-bars').isDisabled(),false);
    await page.locator('#ai-bars').fill('6');
    await page.locator('#ai-extract').click();
    await page.waitForFunction(()=>!document.querySelector('#error').hidden);
    assert.equal(extractionRequests.at(-1).bars,6);
    await page.locator('#dismiss-error').click();
    await page.locator('#ai-override-bars').click();
    await page.locator('#ai-provider').selectOption('Codex');
    // Backend timing has its own cancellation/retention test. Here verify its
    // presentation without making a long-running AI request.
    let paused=false;
    const pauseCommands=[];
    await page.route('**/api/command',async route=>{
      const data=route.request().postDataJSON();
      if(['pause-ai','resume-ai'].includes(data.action)) {
        pauseCommands.push(data.action);paused=data.action==='pause-ai';
        await route.fulfill({status:200,contentType:'application/json',body:'{}'});
      } else await route.fallback();
    });
    await page.route('**/api/state',async route=>{
      const response=await route.fetch();const body=await response.json();
      body.elapsedSeconds=125;
      body.busy=true;body.progress=8/19;
      body.status='Transcribing score · 8/19 batches completed · 62 bars/rows saved';
      body.aiPause={requested:paused,active:0,seconds:0};
      if(paused)body.status='Paused. No AI requests are running. Click Resume to continue.';
      await route.fulfill({response,json:body});
    });
    await page.waitForFunction(()=>document.querySelector('#elapsed-time').textContent==='Time taken: 00:02:05');
    assert.ok((await page.locator('#status').textContent()).includes('8/19 batches completed'));
    assert.equal(await page.locator('#progress').evaluate(e=>e.value),8/19);
    await page.locator('#pause-ai').click();
    await page.waitForFunction(()=>document.querySelector('#pause-ai').textContent==='Resume');
    assert.ok((await page.locator('#status').textContent()).startsWith('Paused.'));
    await page.locator('#pause-ai').click();
    await page.waitForFunction(()=>document.querySelector('#pause-ai').textContent==='Pause');
    assert.deepEqual(pauseCommands,['pause-ai','resume-ai']);
    await page.unroute('**/api/state');
    await page.route('**/api/state',async route=>{
      // A poll can race the route swap above; never let a disposed response fail the run.
      try {const response=await route.fetch();const body=await response.json();body.elapsedSeconds=125;await route.fulfill({response,json:body});}
      catch {await route.continue().catch(()=>{});}
    });
    await page.waitForFunction(()=>!document.querySelector('#play').disabled);
    for(const size of [{width:1440,height:940},{width:1280,height:720}]) {
      await page.setViewportSize(size);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),'Desktop must not have an outer vertical scrollbar');
      assert.ok(await page.locator('.capture-sidebar').evaluate(e=>e.scrollHeight>e.clientHeight),'Sidebar still scrolls');
    }
    await page.locator('#play').click();
    await page.waitForFunction(()=>!!document.querySelector('#play .pause-icon'));
    assert.equal(await page.locator('#play .pause-icon').evaluate(e=>getComputedStyle(e).borderLeftWidth),'4px');
    await page.screenshot({path:path.join(folder,'pause-control.png')});
    await page.locator('#play').click();
    await page.setViewportSize({width:1440,height:940});
    await page.locator('#ai-instructions').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(folder,'capture.png'),fullPage:true});
    await app.evaluate(({dialog},filename)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[filename]});},fixture);
    await page.locator('#open-project').click();
    await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden && document.querySelectorAll('.line-item').length===3);
    assert.equal(await page.locator('#ai-page-controls').isVisible(),true);
    assert.equal(await page.locator('#edit-line').isDisabled(),true);
    await page.locator('#pdf-title').fill(title);
    await page.locator('#ai-song-info').fill('4/4 | Quarter note = 145 | Bass TAB');
    await page.locator('#ai-subtitle').fill('Custom subtitle');
    await page.locator('#ai-footer').fill('Technique legend\nSource note');
    await page.locator('#ai-preview').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open);
    await page.locator('#print-preview img').first().waitFor();
    await page.waitForFunction(()=>document.querySelector('#print-preview img').naturalWidth>0);
    assert.ok((await page.locator('#print-preview-summary').textContent()).includes('PDF pages'));
    await page.screenshot({path:path.join(folder,'pdf-preview.png')});
    await page.locator('#close-print-preview').click();
    await page.locator('#duplicate-line').click();
    await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===4);
    await page.locator('#include-line').click();
    await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===3);
    await page.locator('#ai-review-override').click();
    assert.equal(await page.locator('#ai-merge-rests').isChecked(),true,'Override merges rest runs by default');
    await page.locator('#ai-merge-rests').uncheck();
    await page.locator('#ai-review-bars').fill('2');
    await page.locator('#ai-apply-layout').click();
    await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===5 && document.querySelector('#cancel').hidden);
    await page.locator('#ai-merge-rests').check();
    await page.locator('#ai-apply-layout').click();
    // Bars 1-7 of the fixture are whole rests: one printed block plus bar 8, then 9-10.
    await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===2 && document.querySelector('#cancel').hidden);
    await page.locator('#ai-merge-rests').uncheck();
    await page.locator('#ai-apply-layout').click();
    await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===5 && document.querySelector('#cancel').hidden);
    await app.evaluate(({session},folder)=>session.defaultSession.on('will-download',(_e,item)=>item.setSavePath(`${folder}/${item.getFilename()}`)),folder);
    await app.evaluate(({session})=>{global.aiTestDownloads=[];session.defaultSession.on('will-download',(_e,item)=>item.once('done',(_event,status)=>global.aiTestDownloads.push(status)));});
    await page.locator('#export-pdf').click();
    await page.waitForFunction(name=>document.querySelector('#status').textContent.includes(name+'.pdf'),title);
    await page.waitForFunction(()=>document.querySelector('#cancel').hidden);
    const pdfDeadline=Date.now()+10000;
    while ((await app.evaluate(()=>global.aiTestDownloads.length))<1 && Date.now()<pdfDeadline) await page.waitForTimeout(100);
    assert.deepEqual(await app.evaluate(()=>global.aiTestDownloads),['completed']);
    await page.locator('#save-project').click();
    await page.waitForFunction(name=>document.querySelector('#status').textContent.includes(name+'.drumscore'),title);
    await page.waitForFunction(()=>document.querySelector('#cancel').hidden);
    const deadline=Date.now()+10000;
    while ((await app.evaluate(()=>global.aiTestDownloads.length))<2 && Date.now()<deadline) await page.waitForTimeout(100);
    assert.deepEqual(await app.evaluate(()=>global.aiTestDownloads),['completed','completed']);
    await page.screenshot({path:path.join(folder,'review.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(folder,'mobile-review.png'),fullPage:true});
    assert.equal(await page.locator('#elapsed-time').isVisible(),true);
    await page.setViewportSize({width:1440,height:940});
    for (const instrument of ['piano','drums','chord']) {
      const sample=JSON.parse(JSON.stringify(example));
      sample.meta.instrument=instrument;sample.layout.title=`${instrument} packaged fixture`;
      sample.layout.song_info='';sample.layout.show_metadata=false;
      sample.bars=sample.bars.slice(0,3);
      sample.bars.forEach(b=>{b.system_end=b.number===3;b.events=[{onset:0,duration:4,staff:1,voice:1,notes:[],marks:''}];if(instrument==='piano')b.events.push({...b.events[0],staff:2});});
      if(instrument==='chord') {sample.bars=[];sample.lead_lines=[{number:1,timestamp:0,confidence:1,issues:[],section:'Verse',segments:[{chord:'Am',lyric:'Test lyrics'},{chord:'G',lyric:' and chords'}]}];}
      const samplePath=path.join(folder,`${instrument}.aiscore.json`);
      fs.writeFileSync(samplePath,JSON.stringify(sample));
      await app.evaluate(({dialog},filename)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[filename]});},samplePath);
      await page.locator('#open-project').click();
      await page.waitForFunction(value=>document.querySelector('#pdf-title').value===value && document.querySelectorAll('.line-item').length===1,sample.layout.title);
      await page.locator('#ai-preview').click();
      await page.waitForFunction(()=>document.querySelector('#print-preview').open && document.querySelector('#print-preview img')?.naturalWidth>0);
      await page.screenshot({path:path.join(folder,`${instrument}-preview.png`)});
      await page.locator('#close-print-preview').click();
    }
    assert.deepEqual(errors,[]);
    console.log('Integrated AI desktop checks passed: connections, source rows, page settings, vector export, portable project, responsive UI.');
  } catch(error) {
    console.error(await page.locator('#status').textContent(), await page.locator('#error-text').textContent());
    await page.screenshot({path:path.join(folder,'failure.png'),fullPage:true});
    throw error;
  } finally {await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
