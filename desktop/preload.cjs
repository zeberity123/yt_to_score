const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('desktop', {
  getLanguage: () => ipcRenderer.invoke('get-language'),
  setLanguage: language => ipcRenderer.invoke('set-language', language),
  chooseFile: kind => ipcRenderer.invoke('choose-file', kind === 'project' ? 'project' : 'video'),
});
