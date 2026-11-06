const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('baseball', {
  open: () => ipcRenderer.invoke('record:open'),
  reload: () => ipcRenderer.invoke('record:reload'),
  current: () => ipcRenderer.invoke('record:current'),
  cancel: () => ipcRenderer.invoke('record:cancel'),
  chunk: index => ipcRenderer.invoke('record:chunk', index),
  seek: tick => ipcRenderer.invoke('record:seek', tick),
  profile: () => ipcRenderer.invoke('viewer:profile'),
  onLoaded: fn => { const cb = (_event, value) => fn(value); ipcRenderer.on('record:loaded', cb); return () => ipcRenderer.removeListener('record:loaded', cb); },
  onProgress: fn => { const cb = (_event, value) => fn(value); ipcRenderer.on('record:progress', cb); return () => ipcRenderer.removeListener('record:progress', cb); },
  onError: fn => { const cb = (_event, value) => fn(value); ipcRenderer.on('record:error', cb); return () => ipcRenderer.removeListener('record:error', cb); },
});
