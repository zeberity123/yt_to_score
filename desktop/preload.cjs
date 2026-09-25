const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('desktop', {
  chooseFile: kind => ipcRenderer.invoke('choose-file', kind === 'project' ? 'project' : 'video'),
});
