const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'..');

(async () => {
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const profile=`--user-data-dir=${path.join(root,'diagnostics',executablePath ? 'cleanup-packaged-profile' : 'cleanup-profile')}`;
  const app=await electron.launch({executablePath,args:executablePath ? [profile] : [root,profile],cwd:root});
  const page=await app.firstWindow();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const state=()=>page.evaluate(async () => (await fetch('/api/state',{
    headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}
  })).json());
  async function open(filename) {
    await app.evaluate(({dialog},filename)=>{
      dialog.showOpenDialog=async()=>({canceled:false,filePaths:[filename]});
    },path.join(root,filename));
    await page.locator('#open-project').click();
    await page.waitForFunction(()=>!document.querySelector('#save-project').disabled);
  }
  try {
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    await open('screen_sample/ado_cleanup_v014.drumscore');
    let result=await state();
    assert.equal(result.originalMissing,0);
    assert.deepEqual(result.lines[1].bar_numbers,[5,6,7,8]);
    await page.locator('.line-item').nth(1).click();
    // Deliver an idle status captured before the command after it has started.
    // This used to clear the pending preview job and leave the dialog closed.
    let releasePoll, heldResolve, intercepted=false;
    const held=new Promise(resolve=>heldResolve=resolve);
    const release=new Promise(resolve=>releasePoll=resolve);
    await page.route('**/api/state',async route=>{
      if (intercepted) return route.continue();
      intercepted=true;
      const response=await route.fetch();
      heldResolve();
      await release;
      await route.fulfill({response});
    });
    await held;
    await page.locator('#preview-print').click();
    releasePoll();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open,null,{timeout:60000});
    await page.unroute('**/api/state');
    const white=(await state()).printPreview;
    assert.ok(white.bars.every(n=>n<=4 && n>0));
    assert.deepEqual(white.notes,[]);
    await page.locator('#print-preview').evaluate(dialog=>dialog.close());
    await page.locator('#background').selectOption('original');
    await page.waitForFunction(()=>{
      const img=document.querySelector('#line-image');
      if (!img.complete || !img.naturalWidth) return false;
      const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
      const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
      let colored=0;
      for (let i=0;i<pixels.length;i+=4) if (Math.max(...pixels.slice(i,i+3))-Math.min(...pixels.slice(i,i+3))>20) colored++;
      return colored>100;
    });
    assert.ok(await page.locator('#original-missing').isHidden());
    await page.locator('#preview-print').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open,null,{timeout:60000});
    const original=(await state()).printPreview;
    assert.deepEqual(original.bars,white.bars);
    assert.deepEqual(original.sizes,white.sizes);
    await page.screenshot({path:path.join(root,'diagnostics','ado_cleanup','original-print-ui.png')});
    await page.locator('#print-preview').evaluate(dialog=>dialog.close());
    await page.locator('#background').selectOption('black');
    await page.waitForFunction(()=>document.querySelector('#background').value==='black' && !document.querySelector('#preview-print').disabled);
    await page.locator('#background').selectOption('white');
    await open('diagnostics/ado_cleanup/user_retry/project.json');
    await page.waitForFunction(()=>!document.querySelector('#original-missing').hidden);
    assert.ok((await state()).originalMissing>0);
    for (const language of ['ko','ja','en']) {
      await page.locator('#language').selectOption(language);
      await page.waitForTimeout(100);
      assert.ok((await page.locator('#original-missing').textContent()).length>20);
    }
    assert.deepEqual(errors,[]);
    console.log('Passed: verified four-bar layout, real source-color Off mode, matching PDF-preview geometry, Black/White switching, and old-project notice.');
  } catch (error) {
    const result=await state();
    console.error({status:result.status,error:result.error,busy:result.busy,project:result.projectId,bars:result.barsPerLine,preview:!!result.printPreview});
    throw error;
  } finally {await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
