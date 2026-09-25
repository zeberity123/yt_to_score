const {_electron:electron} = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const root=path.resolve(__dirname,'..');
(async () => {
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const profile=path.join(root,'diagnostics','guitar-ui-profile');
  const app=await electron.launch({executablePath,args:executablePath?[`--user-data-dir=${profile}`]:[root,`--user-data-dir=${profile}`],cwd:root});
  const page=await app.firstWindow();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try {
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    await page.locator('#language').selectOption('ko');
    for (const name of ['t_dHA1lgeAU','UDdLxCuqRQ8']) {
      await page.locator('#capture-tab').click();
      await page.locator('#notation').selectOption('guitar');
      await page.locator('#source').fill(path.join(root,'diagnostics','guitar',`${name}-av.mp4`));
      await page.locator('#load-video').click();
      await page.waitForFunction(()=>!document.querySelector('#detect').disabled,null,{timeout:60000});
      await page.locator('#advanced').evaluate(node=>node.open=true);
      await page.locator('#end').fill('26');
      await page.locator('#extract').click();
      await page.waitForFunction(()=>!document.querySelector('#review-screen').hidden,null,{timeout:90000});
      const count=await page.locator('.line-item').count();
      assert.ok(count>=4 && count<=6,`${name}: ${count}`);
      await page.locator('#edit-line').click();
      await page.waitForFunction(()=>document.querySelector('#editor-image').naturalWidth>0);
      assert.equal(await page.locator('#editor-image').evaluate(node=>node.naturalWidth),1920);
      await page.locator('#cancel-edit').click();
      await page.screenshot({path:path.join(root,'diagnostics',`${name}-korean-review.png`)});
    }
    await app.evaluate(({session},folder)=>{
      globalThis.guitarDownloadState = 'waiting';
      session.defaultSession.once('will-download',(_event,item)=>{
        globalThis.guitarDownloadState = 'started';
        item.setSavePath(`${folder}/${item.getFilename()}`);
        item.once('done',(_event,state)=>globalThis.guitarDownloadState=state);
      });
    },path.join(root,'diagnostics'));
    const title=`기타 ギター TAB ${Date.now()}`;
    await page.locator('#pdf-title').fill(title);
    await page.locator('#export-pdf').click();
    await page.waitForFunction(title=>document.querySelector('#status').textContent.includes(`${title}.pdf`),title);
    await page.waitForFunction(()=>!document.querySelector('#export-pdf').disabled);
    for (let i=0;i<300 && await app.evaluate(()=>globalThis.guitarDownloadState)!=='completed';i++) await new Promise(resolve=>setTimeout(resolve,100));
    assert.equal(await app.evaluate(()=>globalThis.guitarDownloadState),'completed');
    assert.ok(fs.statSync(path.join(root,'diagnostics',`${title}.pdf`)).size>1000);
    assert.deepEqual(errors,[]);
    console.log('Passed: both guitar examples, automatic crop, TAB extraction, retained source editing, Korean UI and CJK PDF title.');
  } finally {await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
