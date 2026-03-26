const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron')
const { spawn, execSync, execFile } = require('child_process')
const path = require('path')
const http = require('http')
const fs = require('fs')

const PORT = 8080
const SERVER_URL = `http://127.0.0.1:${PORT}`

const SERVER_BIN = 'TrackFlowServer'
const AGENT_BIN = 'TrackFlowAgent'

// --- Kill helpers ---
function killByName(name) {
  try {
    execSync(`pkill -f "${name}"`, { stdio: 'ignore' })
    console.log(`Killed ${name}`)
  } catch (e) { /* not running */ }
}

function killByPort(port) {
  try {
    execSync(`lsof -t -i :${port} | xargs kill -9`, { stdio: 'ignore' })
    console.log(`Killed processes on port ${port}`)
  } catch (e) { /* no process on port */ }
}

function killByScript(scriptName) {
  try {
    execSync(`pgrep -f "${scriptName}" | xargs kill -9`, { stdio: 'ignore' })
    console.log(`Killed script ${scriptName}`)
  } catch (e) { /* not running */ }
}

function cleanupOldProcesses() {
  killByName(SERVER_BIN)
  killByName(AGENT_BIN)
  killByName('TrackFlowDaVinci')
  killByPort(PORT)
  killByPort(5173) // Frontend dev server
  killByPort(10101) // Legacy proxy
  killByScript('collector_windows') // Legacy python processes
  killByScript('uvicorn')
}

// --- Kill child processes (SYNCHRONOUS — blocks until dead) ---
function killProcesses() {
  app.isQuitting = true

  // 1. Kill tracked child processes by PID
  for (const proc of [serverProcess, agentProcess, davinciProcess]) {
    if (proc && proc.pid) {
      try {
        execSync(`kill -9 ${proc.pid}`, { stdio: 'ignore' })
      } catch (e) { /* already dead */ }
    }
  }
  serverProcess = null
  agentProcess = null
  davinciProcess = null

  // 2. Kill by executable name (packaged mode)
  killByName(SERVER_BIN)
  killByName(AGENT_BIN)
  killByName('TrackFlowDaVinci')

  // 3. Kill by port
  killByPort(PORT)
  killByPort(5173)

  // 4. Kill python dev processes by script name
  killByScript('uvicorn')
}

// --- macOS startup registry ---
function addToStartup() {
  try {
    app.setLoginItemSettings({
      openAtLogin: true,
      openAsHidden: true
    })
    const settings = app.getLoginItemSettings()
    console.log(`Added to macOS login items (openAtLogin=${settings.openAtLogin})`)
  } catch (e) {
    console.error('Failed to add to login items:', e.message)
  }
}

function removeFromStartup() {
  try {
    app.setLoginItemSettings({
      openAtLogin: false
    })
    const settings = app.getLoginItemSettings()
    console.log(`Removed from macOS login items (openAtLogin=${settings.openAtLogin})`)
  } catch (e) {}
}

// --- Get macOS Machine GUID ---
function getMachineGuid() {
  try {
    const out = execSync(
      `ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, "\\\""); printf("%s\\n", line[4]); }'`,
      { encoding: 'utf-8' }
    )
    if (out && out.trim()) return out.trim()
  } catch (e) { /* fallback */ }
  return null
}

// --- Fetch device role from backend ---
function fetchDeviceRole(machineGuid) {
  return new Promise((resolve) => {
    http.get(`${SERVER_URL}/api/v1/device-role/${machineGuid}`, (res) => {
      let body = ''
      res.on('data', (chunk) => { body += chunk })
      res.on('end', () => {
        try {
          const data = JSON.parse(body)
          resolve(data.role || null)
        } catch (e) {
          resolve(null)
        }
      })
    }).on('error', () => resolve(null))
  })
}

// --- Poll until role is available (agent may still be registering) ---
async function waitForRole(machineGuid, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    const role = await fetchDeviceRole(machineGuid)
    if (role) {
      console.log(`Device role: ${role}`)
      return role
    }
    console.log(`Waiting for agent registration... (${i + 1}/${maxAttempts})`)
    await new Promise(r => setTimeout(r, 2000))
  }
  console.log('Could not determine role, defaulting to employee')
  return 'employee'
}

let mainWindow = null
let tray = null
let serverProcess = null
let agentProcess = null
let davinciProcess = null
let deviceRole = null

// --- Locate bundled binaries ---
function getResourcePath(filename) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'server', filename)
  }
  return path.join(__dirname, '..', 'dist_bin_mac', filename)
}

function installAdobePlugin() {
  try {
    const source = app.isPackaged
      ? path.join(process.resourcesPath, 'server', 'adobe-plugin')
      : path.join(__dirname, '..', 'adobe-plugin')
    const target = path.join(app.getPath('home'), 'Library', 'Application Support', 'Adobe', 'CEP', 'extensions', 'TrackFlow')
    if (!source || !fs.existsSync(source) || !target) return
    fs.mkdirSync(target, { recursive: true })
    fs.cpSync(source, target, { recursive: true, force: true })
    console.log(`Adobe plugin installed: ${target}`)
  } catch (e) {
    console.error(`Adobe plugin install failed: ${e.message}`)
  }
}

// --- Start FastAPI Server ---
function startServer() {
  const serverPath = getResourcePath(SERVER_BIN)
  
  // Ensure executable permissions on Mac
  if (!app.isPackaged && fs.existsSync(serverPath)) {
    try { fs.chmodSync(serverPath, '755') } catch (e) {}
  }

  console.log(`Starting server: ${serverPath}`)
  serverProcess = execFile(serverPath, [], {
    env: { ...process.env, PORT: String(PORT) }
  })

  serverProcess.stdout?.on('data', (data) => console.log(`[Server] ${data}`))
  serverProcess.stderr?.on('data', (data) => console.error(`[Server] ${data}`))
  serverProcess.on('error', (err) => console.error('Server start error:', err))
  serverProcess.on('exit', (code) => {
    console.log(`Server exited with code ${code}`)
    serverProcess = null
    if (!app.isQuitting) {
      console.log('Auto-restarting server in 2s...')
      setTimeout(() => startServer(), 2000)
    }
  })
}

// --- Start Agent (background tracker) ---
function startAgent() {
  const agentPath = getResourcePath(AGENT_BIN)
  
  // Ensure executable permissions on Mac
  if (!app.isPackaged && fs.existsSync(agentPath)) {
    try { fs.chmodSync(agentPath, '755') } catch (e) {}
  }
  
  console.log(`Starting agent: ${agentPath}`)
  agentProcess = execFile(agentPath, [])
  agentProcess.on('error', (err) => console.error('Agent start error:', err))
  agentProcess.on('exit', (code) => {
    console.log(`Agent exited with code ${code}`)
    agentProcess = null
    if (!app.isQuitting) {
      console.log('Auto-restarting agent in 2s...')
      setTimeout(() => startAgent(), 2000)
    }
  })
}

function startDavinciTracker() {
  const trackerPath = getResourcePath('TrackFlowDaVinci')
  if (!fs.existsSync(trackerPath)) {
    console.log(`DaVinci tracker not found: ${trackerPath}`)
    return
  }
  try { fs.chmodSync(trackerPath, '755') } catch (e) {}
  console.log(`Starting DaVinci tracker: ${trackerPath}`)
  davinciProcess = execFile(trackerPath, [])
  davinciProcess.stdout?.on('data', (data) => console.log(`[DaVinci] ${data}`))
  davinciProcess.stderr?.on('data', (data) => console.error(`[DaVinci] ${data}`))
  davinciProcess.on('error', (err) => console.error('DaVinci tracker start error:', err))
  davinciProcess.on('exit', (code) => {
    console.log(`DaVinci tracker exited with code ${code}`)
    davinciProcess = null
    if (!app.isQuitting) {
      setTimeout(() => startDavinciTracker(), 3000)
    }
  })
}

// --- Wait for server to be ready ---
function waitForServer(retries = 30) {
  return new Promise((resolve, reject) => {
    const check = (attempt) => {
      http.get(`${SERVER_URL}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve()
        } else if (attempt < retries) {
          setTimeout(() => check(attempt + 1), 500)
        } else {
          reject(new Error('Server did not respond'))
        }
      }).on('error', () => {
        if (attempt < retries) {
          setTimeout(() => check(attempt + 1), 500)
        } else {
          reject(new Error('Server unreachable'))
        }
      })
    }
    check(0)
  })
}

// --- Create main window (admin only) ---
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'TrackFlow Dashboard',
    autoHideMenuBar: true,
    backgroundColor: '#0a0a1a',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  })

  mainWindow.loadURL(SERVER_URL)

  mainWindow.webContents.on('did-fail-load', (_e, code, desc) => {
    console.error(`Failed to load: ${desc} (${code})`)
    mainWindow.loadURL(`data:text/html,<html><body style="background:#0a0a1a;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0"><div style="text-align:center"><h1>TrackFlow</h1><p>Server is starting up...</p><p style="color:#888">${desc}</p><p><button onclick="location.reload()" style="padding:10px 24px;background:#6366f1;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:16px">Retry</button></p></div></body></html>`)
  })

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// --- System tray ---
function createTray(role) {
  let iconPath = app.isPackaged
    ? path.join(process.resourcesPath, 'icon.png')
    : path.join(__dirname, 'icon.png')
    
  let icon = nativeImage.createFromPath(iconPath)
  // Mac tray icons should be smaller and optionally template images -> .resize({ width: 16, height: 16 })
  if (!icon.isEmpty()) {
    icon = icon.resize({ width: 16, height: 16 })
    icon.setTemplateImage(true) // Supports Dark/Light mode tinting dynamically on Mac
  } else {
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('TrackFlow')

  const menuItems = []

  if (role === 'admin') {
    menuItems.push({
      label: 'Open Dashboard',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
          mainWindow.focus()
        }
      }
    })
    menuItems.push({ type: 'separator' })
  }

  menuItems.push({
    label: 'Quit TrackFlow',
    click: () => {
      app.isQuitting = true
      app.quit()
    }
  })

  tray.setContextMenu(Menu.buildFromTemplate(menuItems))

  // Double click tray icon doesn't natively map to Mac menubar nicely, but can leave it
  if (role === 'admin') {
    tray.on('double-click', () => {
      if (mainWindow) {
        mainWindow.show()
        mainWindow.focus()
      }
    })
  }
}

// --- App lifecycle ---
app.whenReady().then(async () => {
  // Register login item immediately so first-launch employee setups persist across reboot,
  // even if role detection/startup flow takes time or exits early.
  addToStartup()

  // Hide macOS dock icon optionally if employee
  if (app.dock) app.dock.hide()

  // Kill any old servers/dev processes occupying our ports
  cleanupOldProcesses()

  // Wait for OS to release port 8080
  await new Promise(r => setTimeout(r, 2000))

  // Start server + agent
  startServer()
  startAgent()
  installAdobePlugin()
  startDavinciTracker()

  // Wait for server to be ready
  try {
    await waitForServer(30)
    console.log('Server is ready!')
  } catch (err) {
    console.error('Server failed to start:', err)
  }

  // Determine device role — poll until agent has registered
  const machineGuid = getMachineGuid()
  if (machineGuid) {
    deviceRole = await waitForRole(machineGuid)
  } else {
    console.error('Could not read Machine GUID — defaulting to employee')
    deviceRole = 'employee'
  }

  console.log(`Starting in ${deviceRole} mode`)

  if (deviceRole === 'admin') {
    // ADMIN: Show dashboard, no auto-start on boot
    removeFromStartup()
    createTray('admin')
    createWindow()
    if (app.dock) app.dock.show()
  } else {
    // EMPLOYEE: Hide to tray, auto-start on boot
    addToStartup()
    createTray('employee')
  }
})

app.on('window-all-closed', () => {
  // Typically Mac apps don't exit when all windows close
})

app.on('before-quit', () => {
  app.isQuitting = true
  killProcesses()
})

app.on('will-quit', () => {
  killProcesses()
})

app.on('activate', () => {
  if (deviceRole === 'admin' && mainWindow === null) {
    createWindow()
  }
})

// Prevent multiple instances
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (deviceRole === 'admin' && mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}
