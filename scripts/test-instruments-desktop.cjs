const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const root=path.resolve(__dirname,'..');
const examples={bass:['zuk6TVvOYMU','21XgHm-Oyhc','Qo01L0TLih4','QsCv8s5nTmo','i98e58e5AGY'],piano:['uAQLt5lyyIM','J73Fhk5cTX0','ucx1BYaEGXE']};
const expectedCounts={zuk6TVvOYMU:2,'21XgHm-Oyhc':3,Qo01L0TLih4:3,QsCv8s5nTmo:4,i98e58e5AGY:4,uAQLt5lyyIM:3,J73Fhk5cTX0:3,ucx1BYaEGXE:6};
(async()=>{
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const profile=path.join(root,'diagnostics','instruments-ui-profile');
  const app=await electron.launch({executablePath,args:executablePath?[`--user-data-dir=${profile}`]:[root,`--user-data-dir=${profile}`],cwd:root});
  const page=await app.firstWindow();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try {
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    for(const [language,labels] of [['en',['Drums','Bass','Piano']],['ko',['드럼','베이스','피아노']],['ja',['ドラム','ベース','ピアノ']]]) {
      await page.locator('#language').selectOption(language);
      for(const [index,kind] of ['staff','bass','piano'].entries())
        await page.waitForFunction(({kind,label})=>document.querySelector(`#notation option[value="${kind}"]`).textContent===label,{kind,label:labels[index]});
    }
    await page.locator('#language').selectOption('en');
    await app.evaluate(({session},folder)=>{
      globalThis.instrumentDownloads={};
      session.defaultSession.on('will-download',(_event,item)=>{
        item.setSavePath(`${folder}/${item.getFilename()}`);
        item.once('done',(_event,state)=>globalThis.instrumentDownloads[item.getFilename()]=state);
      });
    },path.join(root,'diagnostics'));
    for(const [kind,names] of Object.entries(examples)) {
      for(const name of names) {
        await page.locator('#capture-tab').click();
        await page.locator('#notation').selectOption(kind);
        await page.locator('#source').fill(path.join(root,'diagnostics','instruments',`${name}-av.mp4`));
        await page.locator('#load-video').click();
        await page.waitForFunction(()=>!document.querySelector('#detect').disabled,null,{timeout:60000});
        await page.locator('#advanced').evaluate(node=>node.open=true);
        await page.locator('#end').fill('26');
        await page.locator('#extract').click();
        await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden,null,{timeout:120000});
        const count=await page.locator('.line-item').count();
        assert.equal(count,expectedCounts[name],`${name}: unexpected duplicate or missing capture`);
        if(name==='QsCv8s5nTmo') {
          const state=await page.evaluate(async()=>await (await fetch('/api/state',{
            headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}
          })).json());
          assert.ok(state.warnings.some(warning=>warning.includes('Joined 2 overlapping TAB')));
        }
        await page.locator('#edit-line').click();
        await page.waitForFunction(()=>document.querySelector('#editor-image').naturalWidth>0);
        assert.ok(await page.locator('#editor-image').evaluate(node=>node.naturalWidth>=1080));
        await page.locator('#cancel-edit').click();
        await page.screenshot({path:path.join(root,'diagnostics',`${name}-review.png`)});
        console.log(`${kind}: ${name}, ${count} lines, source editing available`);
      }
      const title=`${kind}-roundtrip-${Date.now()}`;
      await page.locator('#pdf-title').fill(title);
      for(const [button,extension] of [['save-project','drumscore'],['export-pdf','pdf']]) {
        await page.locator(`#${button}`).click();
        for(let i=0;i<300 && await app.evaluate((_,name)=>globalThis.instrumentDownloads[name],`${title}.${extension}`)!=='completed';i++)
          await new Promise(resolve=>setTimeout(resolve,100));
        assert.equal(await app.evaluate((_,name)=>globalThis.instrumentDownloads[name],`${title}.${extension}`),'completed');
        assert.ok(fs.statSync(path.join(root,'diagnostics',`${title}.${extension}`)).size>1000);
      }
      await page.locator('#capture-tab').click();
      await page.locator('#notation').selectOption('staff');
      await app.evaluate(({dialog},filename)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[filename]});},path.join(root,'diagnostics',`${title}.drumscore`));
      await page.locator('#open-project').click();
      await page.waitForFunction(kind=>document.querySelector('#notation').value===kind,kind);
      assert.equal(await page.locator('#pdf-title').inputValue(),title);
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.setViewportSize({width:1280,height:800});
    }
    assert.deepEqual(errors,[]);
    console.log('Passed: all eight bass/piano examples, translations, source editing, export, project notation restoration and mobile layout.');
  } finally {await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
