const { app, BrowserWindow } = require('electron')
const { execSync, execFile } = require('child_process')
const path = require('path')
const http = require('http')

const PORT = 8080
const SERVER_URL = `http://127.0.0.1:${PORT}`

function cleanupOldProcesses() {
  // Kill by process name
  const targets = ['TrackFlowServer', 'TrackFlowAgent']
  for (const name of targets) {
    try {
      execSync(`pkill -f "${name}"`, { stdio: 'ignore' })
      console.log(`Killed old ${name}`)
    } catch (e) { /* not running */ }
  }
  // Also kill anything holding our ports (old instances, dev servers)
  for (const port of [PORT, 10101, 5173]) {
    try {
      execSync(`lsof -ti :${port} | xargs kill -9`, { stdio: 'ignore' })
      console.log(`Killed process on port ${port}`)
    } catch (e) { /* no process on port */ }
  }
}

let mainWindow = null
let serverProcess = null
let agentProcess = null

function getResourcePath(filename) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'server', filename)
  }
  return path.join(__dirname, 'bin', filename)
}

function startServer() {
  const serverPath = getResourcePath('TrackFlowServer')
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
  })
}

function startAgent() {
  const agentPath = getResourcePath('TrackFlowAgent')
  console.log(`Starting agent: ${agentPath}`)

  agentProcess = execFile(agentPath, [], {})
  agentProcess.on('error', (err) => console.error('Agent start error:', err))
  agentProcess.on('exit', (code) => {
    console.log(`Agent exited with code ${code}`)
    agentProcess = null
  })
}

function waitForServer(retries = 30) {
  return new Promise((resolve, reject) => {
    const check = (attempt) => {
      http.get(`${SERVER_URL}/health`, (res) => {
        if (res.statusCode === 200) resolve()
        else if (attempt < retries) setTimeout(() => check(attempt + 1), 500)
        else reject(new Error('Server did not respond'))
      }).on('error', () => {
        if (attempt < retries) setTimeout(() => check(attempt + 1), 500)
        else reject(new Error('Server unreachable'))
      })
    }
    check(0)
  })
}

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
  mainWindow.once('ready-to-show', () => mainWindow.show())

  // Hide to dock instead of closing (macOS convention)
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
  })

  // Clear reference when window is actually destroyed
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

app.whenReady().then(async () => {
  cleanupOldProcesses()
  await new Promise(r => setTimeout(r, 1000))

  startServer()
  startAgent()

  try {
    await waitForServer(30)
    console.log('Server is ready!')
  } catch (err) {
    console.error('Server failed to start:', err)
  }

  createWindow()
})

// macOS: don't quit when all windows are closed (keep in dock)
app.on('window-all-closed', () => {})

app.on('before-quit', () => {
  // Allow the close event to pass through so app can actually quit
  app.isQuitting = true
  if (serverProcess) {
    try { process.kill(serverProcess.pid) } catch (e) { /* ignore */ }
    serverProcess = null
  }
})

// macOS: re-show window when clicking dock icon
app.on('activate', () => {
  if (mainWindow === null) createWindow()
  else mainWindow.show()
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
