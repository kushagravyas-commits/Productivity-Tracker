const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron')
const { spawn, execSync, execFile } = require('child_process')
const path = require('path')
const http = require('http')
const fs = require('fs')
const os = require('os')

const PORT = 8080
const SERVER_URL = `http://127.0.0.1:${PORT}`
const STARTUP_KEY = 'TrackFlowDashboard'
const STARTUP_REG_PATH = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'

// --- Kill helpers ---
function killByName(name) {
  try {
    execSync(`taskkill /f /im "${name}"`, { windowsHide: true, stdio: 'ignore' })
    console.log(`Killed ${name}`)
  } catch (e) { /* not running */ }
}

function killByPort(port) {
  try {
    const out = execSync(
      `netstat -ano | findstr LISTENING | findstr ":${port}"`,
      { encoding: 'utf-8', windowsHide: true }
    )
    const pids = new Set()
    for (const line of out.trim().split('\n')) {
      const match = line.match(/:(\d+)\s+\S+\s+LISTENING\s+(\d+)/)
      if (match && match[1] === String(port)) {
        pids.add(match[2])
      }
    }
    for (const pid of pids) {
      if (pid !== '0') {
        try {
          execSync(`taskkill /f /t /pid ${pid}`, { windowsHide: true, stdio: 'ignore' })
          console.log(`Killed PID ${pid} on port ${port}`)
        } catch (e) { /* already dead */ }
      }
    }
  } catch (e) { /* no process on port */ }
}

function killByScript(scriptName) {
  try {
    const out = execSync(
      `wmic process where "CommandLine like '%${scriptName}%'" get ProcessId /format:list`,
      { encoding: 'utf-8', windowsHide: true }
    )
    for (const line of out.split('\n')) {
      const m = line.match(/ProcessId=(\d+)/)
      if (m && m[1] !== '0') {
        try {
          execSync(`taskkill /f /t /pid ${m[1]}`, { windowsHide: true, stdio: 'ignore' })
          console.log(`Killed PID ${m[1]} (${scriptName})`)
        } catch (e) { /* already dead */ }
      }
    }
  } catch (e) { /* not running */ }
}

function cleanupOldProcesses() {
  killByName('TrackFlowServer.exe')
  killByName('TrackFlowAgent.exe')
  killByName('TrackFlowDaVinci.exe')
  killByPort(PORT)
  killByPort(5173)
  killByPort(10101)
  killByScript('collector_windows')
  killByScript('uvicorn')
}

// --- Kill child processes (SYNCHRONOUS — blocks until dead) ---
function killProcesses() {
  app.isQuitting = true

  // 1. Kill tracked child processes by PID
  for (const proc of [serverProcess, agentProcess, davinciProcess]) {
    if (proc && proc.pid) {
      try {
        execSync(`taskkill /f /t /pid ${proc.pid}`, { windowsHide: true, stdio: 'ignore' })
      } catch (e) { /* already dead */ }
    }
  }
  serverProcess = null
  agentProcess = null
  davinciProcess = null

  // 2. Kill by EXE name (packaged mode)
  killByName('TrackFlowServer.exe')
  killByName('TrackFlowAgent.exe')
  killByName('TrackFlowDaVinci.exe')

  // 3. Kill by port (catches any python dev server still alive)
  killByPort(PORT)
  killByPort(5173)

  // 4. Kill python dev processes by script name
  killByScript('collector_windows')
  killByScript('uvicorn')
}

// --- Windows startup registry ---
function addToStartup() {
  try {
    const exePath = app.isPackaged ? process.execPath : `"${process.execPath}" "${path.resolve(__dirname)}"`
    execSync(
      `reg add "${STARTUP_REG_PATH}" /v ${STARTUP_KEY} /t REG_SZ /d "${exePath}" /f`,
      { windowsHide: true, stdio: 'ignore' }
    )
    console.log('Added to Windows startup')
  } catch (e) {
    console.error('Failed to add to startup:', e.message)
  }
}

function removeFromStartup() {
  try {
    execSync(
      `reg delete "${STARTUP_REG_PATH}" /v ${STARTUP_KEY} /f`,
      { windowsHide: true, stdio: 'ignore' }
    )
    console.log('Removed from Windows startup')
  } catch (e) { /* key doesn't exist */ }
}

// --- Get Windows Machine GUID ---
function getMachineGuid() {
  try {
    const out = execSync(
      'reg query "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid',
      { encoding: 'utf-8', windowsHide: true }
    )
    const match = /MachineGuid\s+REG_SZ\s+(.+)/.exec(out)
    if (match) return match[1].trim()
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

// --- Locate bundled EXEs ---
function getResourcePath(filename) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'server', filename)
  }
  return path.join(__dirname, '..', 'dist_bin', filename)
}

function installAdobePlugin() {
  try {
    const source = app.isPackaged
      ? path.join(process.resourcesPath, 'server', 'adobe-plugin')
      : path.join(__dirname, '..', 'adobe-plugin')
    const target = path.join(process.env.APPDATA || '', 'Adobe', 'CEP', 'extensions', 'TrackFlow')
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
  const serverPath = getResourcePath('TrackFlowServer.exe')
  console.log(`Starting server: ${serverPath}`)

  serverProcess = execFile(serverPath, [], {
    windowsHide: true,
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
  const agentPath = getResourcePath('TrackFlowAgent.exe')
  console.log(`Starting agent: ${agentPath}`)

  agentProcess = execFile(agentPath, [], { windowsHide: true })
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
  const trackerPath = getResourcePath('TrackFlowDaVinci.exe')
  if (!fs.existsSync(trackerPath)) {
    console.log(`DaVinci tracker not found: ${trackerPath}`)
    return
  }
  console.log(`Starting DaVinci tracker: ${trackerPath}`)
  davinciProcess = execFile(trackerPath, [], { windowsHide: true })
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
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, 'icon.ico')
    : path.join(__dirname, 'icon.ico')
  let icon = nativeImage.createFromPath(iconPath)
  if (icon.isEmpty()) icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  tray.setToolTip('TrackFlow')

  const menuItems = []

  // Only admin gets "Open Dashboard"
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

  // Only admin can open dashboard by double-clicking tray
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
  // Kill any old servers/dev processes occupying our ports
  cleanupOldProcesses()

  // Wait for OS to release port 8080
  await new Promise(r => setTimeout(r, 2000))

  // Verify port is actually free
  for (let i = 0; i < 10; i++) {
    try {
      execSync(`netstat -ano | findstr LISTENING | findstr ":${PORT} "`, { encoding: 'utf-8', windowsHide: true })
      killByPort(PORT)
      await new Promise(r => setTimeout(r, 1000))
    } catch (e) {
      break
    }
  }

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
  } else {
    // EMPLOYEE: Hide to tray, auto-start on boot
    addToStartup()
    createTray('employee')
    // No window created — runs silently in background
  }
})

app.on('window-all-closed', () => {
  // Don't quit — keep running in tray
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
