// Preload script — runs in renderer context before web page loads
// Currently minimal; can be extended for IPC if needed
const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('trackflow', {
  platform: process.platform,
  isElectron: true,
})
