const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron')
const { spawn, execSync, execFile } = require('child_process')
const path = require('path')
const http = require('http')

const PORT = 8080
const SERVER_URL = `http://127.0.0.1:${PORT}`

// --- Kill old servers/processes before starting fresh ---
function killByName(name) {
  try {
    execSync(`taskkill /f /im "${name}"`, { windowsHide: true, stdio: 'ignore' })
    console.log(`Killed ${name}`)
  } catch (e) { /* not running */ }
}

function killByPort(port) {
  try {
    // Use netstat to find PIDs listening on the port, then kill each one
    const out = execSync(
      `netstat -ano | findstr LISTENING | findstr ":${port}"`,
      { encoding: 'utf-8', windowsHide: true }
    )
    const pids = new Set()
    for (const line of out.trim().split('\n')) {
      // Match lines where the local address ends with :PORT
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
  // Kill packaged EXEs (production)
  killByName('TrackFlowServer.exe')
  killByName('TrackFlowAgent.exe')

  // Kill by port — catches python dev server on 8080 and vite on 5173
  killByPort(PORT)    // 8080 — backend
  killByPort(5173)    // vite dev server
  killByPort(10101)   // old proxy port (legacy)

  // Kill python dev processes by script name (agent has no port)
  killByScript('collector_windows')
  killByScript('uvicorn')
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
    // Auto-restart if not quitting
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
    // Auto-restart if not quitting
    if (!app.isQuitting) {
      console.log('Auto-restarting agent in 2s...')
      setTimeout(() => startAgent(), 2000)
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
  for (const proc of [serverProcess, agentProcess]) {
    if (proc) {
      try {
        process.kill(proc.pid)
        spawn('taskkill', ['/f', '/t', '/pid', String(proc.pid)], { windowsHide: true })
      } catch (e) { /* ignore */ }
    }
  }
  serverProcess = null
  agentProcess = null
}

// --- App lifecycle ---
app.whenReady().then(async () => {
  // Kill any old servers/dev processes occupying our ports
  cleanupOldProcesses()

  // Wait for port 8080 to be free (up to 5 seconds)
  for (let i = 0; i < 10; i++) {
    try {
      execSync(`netstat -ano | findstr LISTENING | findstr ":${PORT}"`, { encoding: 'utf-8', windowsHide: true })
      // Port still occupied, wait
      await new Promise(r => setTimeout(r, 500))
    } catch (e) {
      // findstr returned no match — port is free
      break
    }
  }

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
