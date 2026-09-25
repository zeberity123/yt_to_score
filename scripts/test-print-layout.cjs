const {_electron:electron}=require('playwright');
const path=require('node:path');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const root=path.resolve(__dirname,'..');
(async()=>{
  const executablePath=process.env.SCORE_TEST_EXECUTABLE;
  const profile=path.join(root,'diagnostics','print-layout-profile');
  const app=await electron.launch({executablePath,args:executablePath?[`--user-data-dir=${profile}`]:[root,`--user-data-dir=${profile}`],cwd:root});
  const page=await app.firstWindow();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const state=()=>page.evaluate(async()=>await (await fetch('/api/state',{headers:{'X-Session-Token':sessionStorage.getItem('drum-session')}})).json());
  async function open(filename){
    await app.evaluate(({dialog},filename)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[filename]});},filename);
    await page.locator('#open-project').click();
    await page.waitForFunction(()=>document.querySelectorAll('.line-item').length===10);
  }
  try{
    await page.waitForFunction(()=>!document.querySelector('#open-project').disabled);
    await open(path.join(root,'diagnostics','print-layout-fixture.drumscore'));
    assert.equal(await page.locator('#reflow-bars').isChecked(),false);
    await page.locator('#reflow-bars').check();
    await page.waitForFunction(()=>!document.querySelector('#bars-per-line').disabled);
    assert.equal((await state()).barsPerLine,6);
    await page.locator('#edit-line').click();
    await page.waitForFunction(()=>document.querySelector('#editor-image').naturalWidth>0);
    await page.locator('#line-height').fill('75');
    assert.ok(await page.locator('#editor .crop-fields input, #line-height').evaluateAll(inputs=>inputs.every(input=>parseFloat(getComputedStyle(input).marginTop)>=12)));
    await page.locator('#all-line-heights').check();
    await page.screenshot({path:path.join(root,'diagnostics','print-ratio-editor.png')});
    await page.locator('#apply-edit').click();
    await page.waitForFunction(()=>!document.querySelector('#editor').open);
    assert.ok((await state()).lines.every(line=>line.height_scale===.75));
    await page.waitForFunction(()=>{
      const img=document.querySelector('#line-image');
      return img.naturalWidth && Math.abs(img.clientHeight/img.clientWidth-img.naturalHeight/img.naturalWidth*.75)<.01;
    });
    await page.locator('#preview-print').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open,null,{timeout:60000});
    const preview=(await state()).printPreview;
    assert.ok(preview.widths.length<10);
    assert.ok(preview.bars.every(value=>value>=1 && value<=6));
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('#print-preview-rows img')).slice(0,2).every(img=>img.naturalWidth>0));
    await page.screenshot({path:path.join(root,'diagnostics','six-bar-print-preview.png')});
    const selectedBefore=await page.locator('#preview-title').textContent();
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('#preview-title').textContent(),selectedBefore);
    const firstAnchor=preview.anchors[0];
    await page.locator('#print-preview-rows select').first().selectOption('3');
    await page.waitForFunction(()=>document.querySelector('#print-preview-rows select')?.value==='3' && !document.querySelector('#print-preview-rows select').disabled,null,{timeout:60000});
    const adjusted=(await state()).printPreview;
    assert.equal(adjusted.anchors[0],firstAnchor);
    assert.equal(adjusted.bars[0],3);
    assert.equal(adjusted.widths[0],1);
    assert.equal(adjusted.bars.reduce((a,b)=>a+b,0),preview.bars.reduce((a,b)=>a+b,0));
    const bounds=await page.locator('#print-preview').boundingBox();
    await page.mouse.click(bounds.x+2,bounds.y+2);
    assert.equal(await page.locator('#print-preview').evaluate(dialog=>dialog.open),true);
    await page.mouse.click(2,2);
    await page.waitForFunction(()=>!document.querySelector('#print-preview').open);
    for(const [language,text] of [['ko','TAB 마디 재배치'],['ja','TABの小節を並べ直す'],['en','Arrange TAB bars']]){
      await page.locator('#language').selectOption(language);
      await page.waitForFunction(text=>document.querySelector('#reflow-label').textContent.includes(text),text);
      if(language==='ko') assert.equal(await page.locator('#preview-print').textContent(),'미리보기');
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.locator('#edit-line').click();
      assert.equal(await page.locator('#line-height').inputValue(),'75');
      await page.locator('#cancel-edit').click();
    }
    await page.screenshot({path:path.join(root,'diagnostics','print-layout-mobile.png')});
    await page.setViewportSize({width:1280,height:900});
    const title=`Print layout ${Date.now()}`;
    await page.locator('#pdf-title').fill(title);
    await app.evaluate(({session},folder)=>{
      globalThis.printDownloads={};
      session.defaultSession.on('will-download',(_event,item)=>{
        item.setSavePath(`${folder}/${item.getFilename()}`);
        item.once('done',(_event,status)=>globalThis.printDownloads[item.getFilename()]=status);
      });
    },path.join(root,'diagnostics'));
    for(const [button,extension] of [['save-project','drumscore'],['export-pdf','pdf']]){
      await page.locator(`#${button}`).click();
      for(let i=0;i<600 && await app.evaluate((_,name)=>globalThis.printDownloads[name],`${title}.${extension}`)!=='completed';i++)await new Promise(resolve=>setTimeout(resolve,100));
      assert.equal(await app.evaluate((_,name)=>globalThis.printDownloads[name],`${title}.${extension}`),'completed');
      assert.ok(fs.statSync(path.join(root,'diagnostics',`${title}.${extension}`)).size>1000);
    }
    await open(path.join(root,'diagnostics',`${title}.drumscore`));
    assert.equal((await state()).barsPerLine,6);
    assert.ok((await state()).lines.every(line=>line.height_scale===.75));
    await page.locator('#preview-print').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open);
    assert.equal((await state()).printPreview.overrides[0],3);
    await page.locator('#print-preview-rows select').first().selectOption('0');
    await page.waitForFunction(()=>document.querySelector('#print-preview-rows select')?.value==='0' && !document.querySelector('#print-preview-rows select').disabled,null,{timeout:60000});
    assert.deepEqual((await state()).printPreview.bars,preview.bars);
    await page.locator('#close-print-preview').click();
    await page.locator('#edit-line').click();
    await page.locator('#reset-line').click();
    await page.waitForFunction(()=>!document.querySelector('#editor').open);
    assert.equal((await state()).lines[0].height_scale,1);
    assert.equal((await state()).lines[1].height_scale,.75);
    await page.locator('#reflow-bars').uncheck();
    await page.waitForFunction(()=>document.querySelector('#bars-per-line').disabled);
    assert.equal(await page.locator('#reflow-help').isVisible(),true);
    await page.locator('#preview-print').click();
    await page.waitForFunction(()=>document.querySelector('#print-preview').open);
    assert.equal((await state()).printPreview.widths.length,10);
    assert.deepEqual(errors,[]);
    console.log('Passed: saved captures, six-bar layout and preview, ratio editing/all lines/reset, PDF export, project round trip, translations, and mobile layout.');
  }finally{await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
