const {spawnSync} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
if (process.platform !== 'win32') throw new Error('Build on Windows x64.');
const python = path.join(root, '.venv', 'Scripts', 'python.exe');
function run(executable, args, extra = {}) {
  const result = spawnSync(executable, args, {cwd:root, stdio:'inherit', windowsHide:true, ...extra});
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
run(python, ['scripts/prepare-build.py']);
fs.mkdirSync(path.join(root, 'build/runtime'), {recursive:true});
fs.copyFileSync(process.execPath, path.join(root, 'build/runtime/node.exe'));
const nodeLicense = ['LICENSE','LICENSE.txt'].map(name => path.join(path.dirname(process.execPath), name)).find(file => fs.existsSync(file));
if (nodeLicense) fs.copyFileSync(nodeLicense, path.join(root, 'build/licenses/Node-LICENSE.txt'));
else run(python, ['-c', 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])',
  `https://raw.githubusercontent.com/nodejs/node/${process.version}/LICENSE`, 'build/licenses/Node-LICENSE.txt']);
run(python, ['-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
  '--name','score-backend','--distpath','build/backend','--workpath','build/pyinstaller','--specpath','build',
  '--paths',root,'--add-data',`${path.join(root,'web')};web`,'--collect-all','imageio_ffmpeg',
  '--collect-all','yt_dlp','--collect-all','yt_dlp_ejs',
  '--exclude-module','tkinter','--exclude-module','pytest','--exclude-module','pymupdf',
  '--exclude-module','IPython','desktop/backend_entry.py']);
run(process.execPath, ['node_modules/electron-builder/cli.js','--win','portable','--x64','--publish','never'], {
  env:{...process.env,ELECTRON_CACHE:path.join(root,'.electron-cache'),
    ELECTRON_BUILDER_CACHE:path.join(root,'.builder-cache'),ELECTRON_BUILDER_COMPRESSION_LEVEL:'5',CSC_IDENTITY_AUTO_DISCOVERY:'false'}
});
