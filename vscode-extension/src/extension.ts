import * as vscode from 'vscode';
import * as http from 'http';
import * as path from 'path';
import * as cp from 'child_process';

function getMachineGuid(): string {
    try {
        if (process.platform === 'win32') {
            const out = cp.execSync('reg query HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography /v MachineGuid').toString();
            const match = /MachineGuid\s+REG_SZ\s+(.+)/.exec(out);
            if (match) return match[1].trim();
        }
    } catch {
        // Fallback
    }
    return vscode.env.machineId; // VS Code's own unique ID as fallback
}

let timer: ReturnType<typeof setInterval> | undefined;
let _lastFailedPayload: { apiUrl: string; context: EditorContext } | null = null;

interface EditorContext {
  captured_at: string;
  editor_app: string;
  workspace: string | null;
  active_file: string | null;
  active_file_path: string | null;
  language: string | null;
  open_files: string[];
  terminal_count: number;
  git_branch: string | null;
  debugger_active: boolean;
}

async function getGitBranch(): Promise<string | null> {
  // Try multiple IDs — 'vscode.git' is standard; forks like Antigravity may differ
  const ids = ['vscode.git', 'git', 'antigravity.git', 'cursor.git'];
  for (const id of ids) {
    try {
      const ext = vscode.extensions.getExtension(id);
      if (!ext) continue;
      // Ensure extension is activated before reading its API
      const api = ext.isActive ? ext.exports : await ext.activate();
      const git = typeof api?.getAPI === 'function' ? api.getAPI(1) : api;
      if (!git?.repositories?.length) continue;
      const branch = git.repositories[0].state?.HEAD?.name;
      if (branch) return branch;
    } catch {
      continue;
    }
  }
  return null;
}

function getEditorApp(): string {
  const appName = vscode.env.appName.toLowerCase();
  if (appName.includes('antigravity')) return 'Antigravity';
  if (appName.includes('cursor')) return 'Cursor';
  if (appName.includes('windsurf')) return 'Windsurf';
  return 'VS Code';
}

function getOpenFiles(): string[] {
  const files: string[] = [];
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

async function collectAndSend(): Promise<void> {
  const config = vscode.workspace.getConfiguration('trackflow');
  const apiUrl: string = config.get('apiUrl') ?? 'http://127.0.0.1:8080';

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

  const context: EditorContext = {
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

function sendPayload(apiUrl: string, context: EditorContext, isRetry = false): void {
  try {
    const body = JSON.stringify(context);
    const url = new URL('/api/v1/context/editor', apiUrl);
    const options: http.RequestOptions = {
      hostname: url.hostname,
      port: parseInt(url.port) || 10101,
      path: url.pathname,
      method: 'POST',
      timeout: 5000,
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
        'X-Machine-GUID': getMachineGuid(),
      },
    };
    const req = http.request(options);
    req.setTimeout(5000, () => {
      req.destroy();
    });
    req.on('error', () => {
      // Queue for retry on next tick (only if this isn't already a retry)
      if (!isRetry) {
        _lastFailedPayload = { apiUrl, context };
      }
    });
    req.on('response', () => {
      // Success — clear retry buffer
      _lastFailedPayload = null;
    });
    req.write(body);
    req.end();
  } catch {
    // Never throw from here
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration('trackflow');
  const intervalMs = ((config.get('intervalSeconds') as number) ?? 5) * 1000;

  // Send immediately on activate
  void collectAndSend();

  // Then poll on interval
  timer = setInterval(() => void collectAndSend(), intervalMs);

  context.subscriptions.push({
    dispose: () => {
      if (timer) clearInterval(timer);
    },
  });

  console.log(`[TrackFlow] Context extension active — polling every ${intervalMs / 1000}s`);
}

export function deactivate(): void {
  if (timer) clearInterval(timer);
}
