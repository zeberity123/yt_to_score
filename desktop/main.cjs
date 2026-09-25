const {app, BrowserWindow, ipcMain, dialog} = require('electron');
const {spawn, spawnSync} = require('node:child_process');
const path = require('node:path');
const crypto = require('node:crypto');
const fs = require('node:fs');
const readline = require('node:readline');

const root = path.resolve(__dirname, '..');
const profile = app.commandLine.getSwitchValue('user-data-dir');
if (profile || app.isPackaged) {
  const userData = profile ? path.resolve(profile) : path.join(app.getPath('appData'), 'Video Sheet to PDF');
  fs.mkdirSync(userData, {recursive:true});
  app.setPath('userData', userData);
}
let backend, window, origin, exportSession;
const preferencesPath = path.join(app.getPath('userData'), 'preferences.json');
let preferences = {};
try { preferences = JSON.parse(fs.readFileSync(preferencesPath, 'utf8')); } catch {}
if (!['en','ko','ja'].includes(preferences.language)) preferences.language = 'en';
function cleanExportSession() {
  if (!exportSession) return;
  const target = path.resolve(exportSession.path);
  if (path.dirname(target) !== path.resolve(exportSession.root) || !path.basename(target).startsWith('session-')) return;
  try { fs.rmSync(target, {recursive:true,force:true,maxRetries:3,retryDelay:100}); } catch {}
}
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();
else {
  app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.focus(); } });
  app.whenReady().then(start).catch(async error => {
    await dialog.showMessageBox({type:'error', title:'Video Sheet to PDF', message:'Could not start the score workspace.', detail:error.message});
    app.quit();
  });
}

async function start() {
  const python = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'score-backend.exe') :
    path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (!fs.existsSync(python)) throw new Error(app.isPackaged ? 'The processing engine is missing. Download the app again.' : 'Run setup.bat first to install the Python processing engine.');
  const token = crypto.randomBytes(32).toString('hex');
  const backendEnv = {...process.env, DRUMSCORE_TOKEN:token, PYTHONIOENCODING:'utf-8'};
  if (app.isPackaged) {
    backendEnv.DRUMSCORE_OUTPUT = path.join(app.getPath('userData'), 'output');
    backendEnv.DRUMSCORE_NODE = path.join(process.resourcesPath, 'runtime', 'node.exe');
  }
  const exportsRoot = path.join(backendEnv.DRUMSCORE_OUTPUT || path.join(root,'output'), 'exports');
  exportSession = {root:exportsRoot,path:path.join(exportsRoot, `session-${crypto.randomUUID()}`)};
  backendEnv.DRUMSCORE_EXPORTS = exportSession.path;
  backend = spawn(python, app.isPackaged ? [] : ['-m','drumscore.server'], {
    cwd:app.isPackaged ? app.getPath('userData') : root, windowsHide:true,
    env:backendEnv, stdio:['ignore','pipe','pipe']});
  backend.once('exit', cleanExportSession);
  let errors = '';
  backend.stderr.on('data', chunk => { errors = (errors+chunk.toString()).slice(-4000); });
  const port = await new Promise((resolve,reject) => {
    const timer = setTimeout(() => reject(new Error('The processing engine did not start in time.')), 30000);
    const lines = readline.createInterface({input:backend.stdout});
    lines.on('line', line => {
      try { const message = JSON.parse(line); if (message.port) { clearTimeout(timer); resolve(message.port); lines.close(); } } catch {}
    });
    backend.once('error', error => { clearTimeout(timer); reject(error); });
    backend.once('exit', code => { clearTimeout(timer); reject(new Error(errors || `Processing engine exited (${code}).`)); });
  });
  origin = `http://127.0.0.1:${port}`;
  window = new BrowserWindow({width:1440,height:940,minWidth:390,minHeight:620,
    title:'Video Sheet to PDF', backgroundColor:'#f5f4f0', autoHideMenuBar:true,
    webPreferences:{preload:path.join(__dirname,'preload.cjs'), contextIsolation:true, nodeIntegration:false, sandbox:true}});
  window.setMenu(null);
  window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
  window.webContents.on('will-navigate', (event,url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
  window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback) => callback(false));
  window.webContents.session.on('will-download', (_event,item) => {
    item.setSaveDialogOptions({defaultPath:path.join(app.getPath('downloads'), item.getFilename())});
    const url = new URL(item.getURL());
    if (url.origin === origin && url.pathname === '/api/download') {
      item.once('done', () => {
        fetch(`${origin}/api/command`, {method:'POST', headers:{'Content-Type':'application/json','X-Session-Token':token},
          body:JSON.stringify({action:'release-artifact',id:url.searchParams.get('id')})}).catch(() => {});
      });
    }
  });
  function checkCaller(event) {
    if (event.sender !== window?.webContents || event.senderFrame !== event.sender.mainFrame || new URL(event.senderFrame.url).origin !== origin) throw new Error('Invalid caller.');
  }
  ipcMain.handle('get-language', event => { checkCaller(event); return preferences.language; });
  ipcMain.handle('set-language', (event,language) => {
    checkCaller(event);
    if (!['en','ko','ja'].includes(language)) throw new Error('Invalid language.');
    const next = {...preferences, language};
    const temporary = preferencesPath + '.tmp';
    try { fs.writeFileSync(temporary, JSON.stringify(next), 'utf8'); fs.renameSync(temporary, preferencesPath); preferences = next; }
    finally { fs.rmSync(temporary, {force:true}); }
  });
  ipcMain.handle('choose-file', async (event,kind) => {
    checkCaller(event);
    const names = {en:['Sheet music project','Videos'],ko:['악보 프로젝트','동영상'],ja:['楽譜プロジェクト','動画']}[preferences.language];
    const filters = kind === 'project' ? [{name:names[0],extensions:['drumscore','json']}] : [{name:names[1],extensions:['mp4','mkv','webm','mov','avi']}];
    const result = await dialog.showOpenDialog(window,{properties:['openFile'], filters});
    return result.canceled ? null : result.filePaths[0];
  });
  backend.on('exit', () => { if (window && !window.isDestroyed()) window.webContents.send('backend-stopped'); });
  await window.loadURL(`${origin}/#${token}`);
}
app.on('before-quit', () => {
  if (backend && !backend.killed && backend.exitCode === null) {
    if (process.platform === 'win32') {
      const result = spawnSync('taskkill', ['/pid',String(backend.pid),'/t','/f'], {windowsHide:true,stdio:'ignore'});
      if (result.status === 0) cleanExportSession();
    }
    else backend.kill();
  }
});
app.on('window-all-closed', () => app.quit());
