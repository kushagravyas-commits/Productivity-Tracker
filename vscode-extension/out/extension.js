"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const http = __importStar(require("http"));
const https = __importStar(require("https"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const cp = __importStar(require("child_process"));
let _machineGuid = null;
let _machineGuidReady = false;
function tryLoadMacGuidFromAgentConfig() {
    try {
        const configPath = path.join(os.homedir(), 'Library', 'Application Support', 'TrackFlow', 'agent_config.json');
        if (!fs.existsSync(configPath))
            return null;
        const raw = fs.readFileSync(configPath, 'utf-8');
        const parsed = JSON.parse(raw);
        const guid = typeof parsed?.machine_guid === 'string' ? parsed.machine_guid.trim() : '';
        return guid || null;
    }
    catch {
        return null;
    }
}
function tryReadMacHardwareGuid() {
    try {
        const out = cp.execSync(`ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, "\\""); printf("%s", line[4]); }'`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
        return out || null;
    }
    catch {
        return null;
    }
}
function getMachineGuid() {
    if (_machineGuid)
        return _machineGuid;
    // Try reading from Windows registry
    try {
        if (process.platform === 'win32') {
            const out = cp.execSync('reg query HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography /v MachineGuid').toString();
            const match = /MachineGuid\s+REG_SZ\s+(.+)/.exec(out);
            if (match) {
                _machineGuid = match[1].trim();
                _machineGuidReady = true;
                return _machineGuid;
            }
        }
    }
    catch {
        // Registry failed — will be resolved by backend fetch
    }
    if (process.platform === 'darwin') {
        const macGuid = tryLoadMacGuidFromAgentConfig();
        if (macGuid) {
            _machineGuid = macGuid;
            _machineGuidReady = true;
            return _machineGuid;
        }
        const hardwareGuid = tryReadMacHardwareGuid();
        if (hardwareGuid) {
            _machineGuid = hardwareGuid;
            _machineGuidReady = true;
            return _machineGuid;
        }
        // On macOS, avoid emitting vscode machineId as device identity.
        // Wait for local TrackFlow agent config / hardware UUID to become readable.
        return '';
    }
    return vscode.env.machineId;
}
function fetchMachineGuidFromBackend(apiUrl, retries = 10) {
    try {
        const url = new URL('/api/v1/machine-guid', apiUrl);
        http.get({ hostname: url.hostname, port: parseInt(url.port) || 8080, path: url.pathname, timeout: 3000 }, (res) => {
            let body = '';
            res.on('data', (chunk) => { body += chunk; });
            res.on('end', () => {
                try {
                    const data = JSON.parse(body);
                    if (data.machine_guid) {
                        if (_machineGuid !== data.machine_guid) {
                            console.log(`[TrackFlow] Synced Machine GUID from backend: ${data.machine_guid}`);
                            _machineGuid = data.machine_guid;
                            _machineGuidReady = true;
                        }
                        return;
                    }
                }
                catch { /* ignore */ }
                // Backend returned null — retry
                if (retries > 0) {
                    setTimeout(() => fetchMachineGuidFromBackend(apiUrl, retries - 1), 3000);
                }
            });
        }).on('error', () => {
            // Backend not ready — retry
            if (retries > 0) {
                setTimeout(() => fetchMachineGuidFromBackend(apiUrl, retries - 1), 3000);
            }
        });
    }
    catch { /* ignore */ }
}
let timer;
let _lastFailedPayload = null;
async function getGitBranch() {
    // Try multiple IDs — 'vscode.git' is standard; forks like Antigravity may differ
    const ids = ['vscode.git', 'git', 'antigravity.git', 'cursor.git'];
    for (const id of ids) {
        try {
            const ext = vscode.extensions.getExtension(id);
            if (!ext)
                continue;
            // Ensure extension is activated before reading its API
            const api = ext.isActive ? ext.exports : await ext.activate();
            const git = typeof api?.getAPI === 'function' ? api.getAPI(1) : api;
            if (!git?.repositories?.length)
                continue;
            const branch = git.repositories[0].state?.HEAD?.name;
            if (branch)
                return branch;
        }
        catch {
            continue;
        }
    }
    return null;
}
function getEditorApp() {
    const appName = vscode.env.appName.toLowerCase();
    if (appName.includes('antigravity'))
        return 'Antigravity';
    if (appName.includes('cursor'))
        return 'Cursor';
    if (appName.includes('windsurf'))
        return 'Windsurf';
    return 'VS Code';
}
function getOpenFiles() {
    const files = [];
    for (const group of vscode.window.tabGroups.all) {
        for (const tab of group.tabs) {
            if (tab.input instanceof vscode.TabInputText) {
                files.push(path.basename(tab.input.uri.fsPath));
            }
        }
    }
    // Deduplicate
    return [...new Set(files)];
}
async function collectAndSend() {
    const config = vscode.workspace.getConfiguration('trackflow');
    const apiUrl = config.get('apiUrl') ?? 'http://127.0.0.1:8080';
    // Retry last failed payload before collecting new one
    if (_lastFailedPayload) {
        const retry = _lastFailedPayload;
        _lastFailedPayload = null;
        sendPayload(retry.apiUrl, retry.context, true);
    }
    const editor = vscode.window.activeTextEditor;
    const activeFile = editor ? path.basename(editor.document.fileName) : null;
    const activeFilePath = editor ? editor.document.fileName : null;
    const language = editor ? editor.document.languageId : null;
    const wsFolder = vscode.workspace.workspaceFolders?.[0];
    const workspace = wsFolder ? wsFolder.name : null;
    const gitBranch = await getGitBranch();
    const context = {
        // Send local device time (no timezone suffix) so admin dashboard shows the user's clock time
        captured_at: (() => { const n = new Date(); return new Date(n.getTime() - n.getTimezoneOffset() * 60000).toISOString().slice(0, 19); })(),
        editor_app: getEditorApp(),
        workspace,
        active_file: activeFile,
        active_file_path: activeFilePath,
        language,
        open_files: getOpenFiles(),
        terminal_count: vscode.window.terminals.length,
        git_branch: gitBranch,
        debugger_active: vscode.debug.activeDebugSession !== undefined,
    };
    sendPayload(apiUrl, context);
}
function sendPayload(apiUrl, context, isRetry = false) {
    try {
        if (process.platform === 'darwin' && !_machineGuidReady) {
            if (!isRetry) {
                _lastFailedPayload = { apiUrl, context };
            }
            return;
        }
        const machineGuid = getMachineGuid();
        if (!machineGuid) {
            if (!isRetry) {
                _lastFailedPayload = { apiUrl, context };
            }
            return;
        }
        const body = JSON.stringify(context);
        const url = new URL('/api/v1/context/editor', apiUrl);
        const isHttps = url.protocol === 'https:';
        const client = isHttps ? https : http;
        const defaultPort = isHttps ? 443 : 80;
        const options = {
            hostname: url.hostname,
            port: url.port ? parseInt(url.port) : defaultPort,
            path: url.pathname,
            method: 'POST',
            timeout: 5000,
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(body),
                'X-Machine-GUID': machineGuid,
            },
        };
        const req = client.request(options);
        req.setTimeout(5000, () => {
            req.destroy();
        });
        req.on('error', () => {
            // Queue for retry on next tick (only if this isn't already a retry)
            if (!isRetry) {
                _lastFailedPayload = { apiUrl, context };
            }
        });
        req.on('response', (res) => {
            // Consume the response stream to free the socket
            res.on('data', () => { });
            res.on('end', () => {
                // Success — clear retry buffer
                _lastFailedPayload = null;
            });
        });
        req.write(body);
        req.end();
    }
    catch {
        // Never throw from here
    }
}
function activate(context) {
    const config = vscode.workspace.getConfiguration('trackflow');
    const intervalMs = (config.get('intervalSeconds') ?? 5) * 1000;
    const apiUrl = config.get('apiUrl') ?? 'http://127.0.0.1:8080';
    // On macOS, use local agent config GUID to avoid binding to server machine identity.
    // Keep backend GUID sync for Windows and other platforms.
    if (process.platform !== 'darwin') {
        fetchMachineGuidFromBackend(apiUrl);
    }
    else {
        getMachineGuid();
    }
    // Send immediately on activate
    void collectAndSend();
    // Then poll on interval
    timer = setInterval(() => void collectAndSend(), intervalMs);
    context.subscriptions.push({
        dispose: () => {
            if (timer)
                clearInterval(timer);
        },
    });
    console.log(`[TrackFlow] Context extension active — polling every ${intervalMs / 1000}s`);
}
function deactivate() {
    if (timer)
        clearInterval(timer);
}
//# sourceMappingURL=extension.js.map