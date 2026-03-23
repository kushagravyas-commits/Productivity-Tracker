const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('trackflow', {
  platform: process.platform,
  isElectron: true,
})
