const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron')
const { spawn, execSync, execFile } = require('child_process')
const path = require('path')
const http = require('http')

const PORT = 8080
const SERVER_URL = `http://127.0.0.1:${PORT}`

// --- Kill old servers/processes before starting fresh ---
function cleanupOldProcesses() {
  const targets = ['TrackFlowServer.exe', 'TrackFlowAgent.exe']
  for (const name of targets) {
    try {
      execSync(`taskkill /f /im "${name}"`, { windowsHide: true, stdio: 'ignore' })
      console.log(`Killed old ${name}`)
    } catch (e) { /* not running, ignore */ }
  }
  // Also kill anything on our ports (dev servers, old instances)
  for (const port of [PORT, 10101, 5173]) {
    try {
      const result = execSync(`netstat -ano | findstr "LISTENING" | findstr ":${port} "`, { encoding: 'utf-8', windowsHide: true })
      const lines = result.trim().split('\n')
      for (const line of lines) {
        const parts = line.trim().split(/\s+/)
        const pid = parts[parts.length - 1]
        if (pid && pid !== '0') {
          try {
            execSync(`taskkill /f /pid ${pid}`, { windowsHide: true, stdio: 'ignore' })
            console.log(`Killed PID ${pid} on port ${port}`)
          } catch (e) { /* ignore */ }
        }
      }
    } catch (e) { /* no process on port, ignore */ }
  }
}

let mainWindow = null
let tray = null
let serverProcess = null
let agentProcess = null

// --- Locate bundled EXEs ---
function getResourcePath(filename) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'server', filename)
  }
  // Dev mode: look in dist_bin
  return path.join(__dirname, '..', 'dist_bin', filename)
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

// --- Create main window ---
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

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // Minimize to tray instead of closing
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
function createTray() {
  // Try to load icon from resources (packaged) or project root (dev)
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, 'icon.ico')
    : path.join(__dirname, 'icon.ico')
  let icon = nativeImage.createFromPath(iconPath)
  if (icon.isEmpty()) icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  tray.setToolTip('TrackFlow Dashboard')

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open Dashboard',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
          mainWindow.focus()
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Quit TrackFlow',
      click: () => {
        app.isQuitting = true
        app.quit()
      }
    }
  ])

  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// --- Kill child processes ---
function killProcesses() {
  if (serverProcess) {
    try {
      process.kill(serverProcess.pid)
      // Also kill by taskkill to ensure child processes are killed
      spawn('taskkill', ['/f', '/t', '/pid', String(serverProcess.pid)], { windowsHide: true })
    } catch (e) { /* ignore */ }
    serverProcess = null
  }
  // Don't kill agent — it should keep running independently
}

// --- App lifecycle ---
app.whenReady().then(async () => {
  // Kill any old servers/dev processes occupying our ports
  cleanupOldProcesses()

  // Small delay to let ports free up
  await new Promise(r => setTimeout(r, 1000))

  // Start server + agent
  startServer()
  startAgent()

  // Wait for server to be ready (up to 15 seconds)
  try {
    await waitForServer(30)
    console.log('Server is ready!')
  } catch (err) {
    console.error('Server failed to start:', err)
  }

  createTray()
  createWindow()
})

app.on('window-all-closed', () => {
  // Don't quit when window is closed (minimize to tray)
})

app.on('before-quit', () => {
  killProcesses()
})

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow()
  }
})

// Prevent multiple instances
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}
