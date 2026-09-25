const {_electron:electron}=require('playwright');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const profile=path.join(root,'diagnostics','loading-profile');
  const app=await electron.launch({executablePath,args:executablePath?[`--user-data-dir=${profile}`]:[root,`--user-data-dir=${profile}`],cwd:root});
  const page=await app.firstWindow(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  try {
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    let releaseCommand,releaseMedia;
    const commandGate=new Promise(resolve=>releaseCommand=resolve);
    const mediaGate=new Promise(resolve=>releaseMedia=resolve);
    await page.route('**/api/command',async route=>{
      if(route.request().postDataJSON().action==='load')await commandGate;
      await route.continue();
    });
    await page.route('**/api/video?*',async route=>{await mediaGate;await route.continue();});
    await page.locator('#source').fill(path.join(root,'samples','kgNjaXTh0rU.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#video-loading').hidden);
    assert.equal(await page.locator('#video-empty').isVisible(),false);
    for(const [language,title] of [['en','Loading video…'],['ko','동영상 불러오는 중…'],['ja','動画を読み込み中…']]) {
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(title=>document.querySelector('#video-loading h2').textContent===title,title);
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    await page.screenshot({path:path.join(root,'diagnostics','loading-japanese-mobile.png')});
    await page.locator('#language').selectOption('en');
    const mediaRequested=page.waitForRequest(request=>request.url().includes('/api/video?'));
    releaseCommand();await mediaRequested;
    await page.waitForFunction(()=>!document.querySelector('#load-video').disabled);
    assert.equal(await page.locator('#video-loading').isVisible(),true,'Wait for first decoded frame');
    releaseMedia();
    await page.waitForFunction(()=>!document.querySelector('#video-fit').hidden&&document.querySelector('#video').readyState>=2);
    assert.equal(await page.locator('#video-loading').isVisible(),false);
    await page.unroute('**/api/command');await page.unroute('**/api/video?*');

    // A failed replacement must restore the existing video, not leave a spinner.
    await page.locator('#source').fill(path.join(root,'diagnostics','missing-loading-test.mp4'));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#error').hidden&&document.querySelector('#video-loading').hidden);
    assert.equal(await page.locator('#video-fit').isVisible(),true);
    await page.locator('#dismiss-error').click();

    // Control the backend duration without downloading a remote video.
    const base=await page.evaluate(async()=>await(await fetch('/api/state',{headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}})).json());
    let busy=false,revision=base.revision;
    await page.route('**/api/state',route=>route.fulfill({json:{...base,busy,error:null,revision,status:busy?'Working…':'Cancelled.'}}));
    await page.route('**/api/command',route=>{
      const action=route.request().postDataJSON().action;
      busy=action==='load';revision++;
      return route.fulfill({json:{ok:true}});
    });
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>!document.querySelector('#cancel').hidden);
    assert.equal(await page.locator('#video-loading').isVisible(),true);
    assert.equal(await page.locator('#video-fit').isVisible(),false);
    await page.locator('#cancel').click();
    await page.waitForFunction(()=>document.querySelector('#video-loading').hidden);
    assert.equal(await page.locator('#video-fit').isVisible(),true);
    await page.unroute('**/api/command');await page.unroute('**/api/state');

    await page.route('**/api/command',route=>route.fulfill({status:400,json:{error:'Test request failure'}}));
    await page.locator('#load-video').click();
    await page.waitForFunction(()=>document.querySelector('#error-text').textContent==='Test request failure');
    assert.equal(await page.locator('#video-loading').isVisible(),false);
    await page.unroute('**/api/command');
    // Browser file uploads use the same loading screen, including upload errors.
    let releaseUpload;
    const uploadGate=new Promise(resolve=>releaseUpload=resolve);
    await page.route('**/api/upload',async route=>{await uploadGate;await route.fulfill({status:400,json:{error:'Test upload failure'}});});
    await page.locator('#video-file').setInputFiles({name:'loading.mp4',mimeType:'video/mp4',buffer:Buffer.from('test')});
    await page.waitForFunction(()=>!document.querySelector('#video-loading').hidden);
    releaseUpload();
    await page.waitForFunction(()=>document.querySelector('#error-text').textContent==='Test upload failure');
    assert.equal(await page.locator('#video-loading').isVisible(),false);
    assert.deepEqual(errors,[]);
    console.log('Passed: immediate loading, first-frame readiness, all languages, mobile layout, replacement failure, cancellation, request failure and upload failure.');
  } finally {await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
