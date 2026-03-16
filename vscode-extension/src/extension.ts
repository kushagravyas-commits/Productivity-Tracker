import * as vscode from 'vscode';
import * as http from 'http';
import * as path from 'path';

let timer: ReturnType<typeof setInterval> | undefined;

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
  const apiUrl: string = config.get('apiUrl') ?? 'http://127.0.0.1:8000';

  const editor = vscode.window.activeTextEditor;
  const activeFile = editor ? path.basename(editor.document.fileName) : null;
  const activeFilePath = editor ? editor.document.fileName : null;
  const language = editor ? editor.document.languageId : null;

  const wsFolder = vscode.workspace.workspaceFolders?.[0];
  const workspace = wsFolder ? wsFolder.name : null;

  const gitBranch = await getGitBranch();

  const context: EditorContext = {
    captured_at: new Date().toISOString(),
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

function sendPayload(apiUrl: string, context: EditorContext): void {
  try {
    const body = JSON.stringify(context);
    const url = new URL('/api/v1/context/editor', apiUrl);
    const options: http.RequestOptions = {
      hostname: url.hostname,
      port: parseInt(url.port) || 8000,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    };
    const req = http.request(options);
    req.on('error', () => { /* Silently swallow — don't disturb the IDE */ });
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
