import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { cadToolEnvironment } from '@main/host/cad/cad-python-environment';
import {
  currentTextToCadLayout,
  findCadPythonExecutable,
  provisionCadRuntime,
} from '@main/host/cad/cad-runtime-service';
import { viewerClientIsBuilt } from '@main/host/cad/text-to-cad-layout';
import { log } from '@main/lib/logger';

const HOST = '127.0.0.1';
const STARTUP_TIMEOUT_MS = 30_000;

export type EnsureCadViewerResult =
  | { success: true; url: string }
  | { success: false; error: string };

type StartCadViewerResult = { success: true; port: number } | { success: false; error: string };

export type CadViewerChild = {
  kill(): boolean;
  onTerminated(listener: () => void): void;
};

/** The launcher's machine-readable last line: `{"url","port","action"}`. */
export interface CadViewerLaunch {
  url: string;
  port: number;
  action: 'started' | 'reused';
}

export function parseCadViewerLaunch(stdout: string): CadViewerLaunch | null {
  for (const line of stdout.split(/\r?\n/).reverse()) {
    const candidate = line.trim();
    if (!candidate.startsWith('{')) continue;
    try {
      const payload: unknown = JSON.parse(candidate);
      if (
        typeof payload === 'object' &&
        payload !== null &&
        'url' in payload &&
        typeof payload.url === 'string' &&
        'port' in payload &&
        typeof payload.port === 'number' &&
        'action' in payload &&
        (payload.action === 'started' || payload.action === 'reused')
      ) {
        return { url: payload.url, port: payload.port, action: payload.action };
      }
    } catch {
      // A partial line; keep looking.
    }
  }
  return null;
}

/**
 * One Viewer per served directory. Jake's launcher owns ports and reuse: a
 * launch from a directory that already has a live Viewer at the same code
 * answers `reused` and exits, so the lifecycle may end up tracking a port it
 * does not own a process for. Only owned children are ever killed.
 */
export class CadViewerProcessLifecycle {
  private viewerProcess: CadViewerChild | null = null;
  private viewerPort: number | null = null;
  private ensurePromise: Promise<StartCadViewerResult> | null = null;

  ensureStarted(input: {
    isHealthy: (port: number) => Promise<boolean>;
    start: () => Promise<StartCadViewerResult>;
  }): Promise<StartCadViewerResult> {
    if (this.ensurePromise) return this.ensurePromise;

    const tracked = this.ensureStartedInternal(input).finally(() => {
      if (this.ensurePromise === tracked) this.ensurePromise = null;
    });
    this.ensurePromise = tracked;
    return tracked;
  }

  adopt(child: CadViewerChild): void {
    if (this.viewerProcess && this.viewerProcess !== child) this.stop();
    this.viewerProcess = child;
    this.viewerPort = null;

    const release = () => {
      if (this.viewerProcess !== child) return;
      this.viewerProcess = null;
      this.viewerPort = null;
    };
    child.onTerminated(release);
  }

  owns(child: CadViewerChild): boolean {
    return this.viewerProcess === child;
  }

  markReady(child: CadViewerChild, port: number): boolean {
    if (!this.owns(child)) return false;
    this.viewerPort = port;
    return true;
  }

  /** Track a Viewer another launch already owns (the launcher answered `reused`). */
  markExternal(port: number): void {
    this.viewerProcess = null;
    this.viewerPort = port;
  }

  get port(): number | null {
    return this.viewerPort;
  }

  stop(child: CadViewerChild | null = this.viewerProcess): void {
    if (child === null && this.viewerProcess === null) {
      this.viewerPort = null;
      return;
    }
    if (!child || this.viewerProcess !== child) return;
    this.viewerProcess = null;
    this.viewerPort = null;
    child.kill();
  }

  private async ensureStartedInternal(input: {
    isHealthy: (port: number) => Promise<boolean>;
    start: () => Promise<StartCadViewerResult>;
  }): Promise<StartCadViewerResult> {
    const currentProcess = this.viewerProcess;
    const currentPort = this.viewerPort;
    if (
      currentPort !== null &&
      (await input.isHealthy(currentPort)) &&
      this.viewerProcess === currentProcess &&
      this.viewerPort === currentPort
    ) {
      return { success: true, port: currentPort };
    }

    this.stop();
    try {
      const started = await input.start();
      if (!started.success) this.stop();
      return started;
    } catch (error) {
      this.stop();
      throw error;
    }
  }
}

export class CadViewerLifecycleRegistry {
  private readonly lifecycles = new Map<string, CadViewerProcessLifecycle>();

  forWorkspace(workspacePath: string): CadViewerProcessLifecycle {
    const key = resolve(workspacePath);
    const existing = this.lifecycles.get(key);
    if (existing) return existing;
    const lifecycle = new CadViewerProcessLifecycle();
    this.lifecycles.set(key, lifecycle);
    return lifecycle;
  }

  stopAll(): void {
    for (const lifecycle of this.lifecycles.values()) lifecycle.stop();
    this.lifecycles.clear();
  }

  get size(): number {
    return this.lifecycles.size;
  }
}

const viewerLifecycles = new CadViewerLifecycleRegistry();
let viewerStartupTail: Promise<void> = Promise.resolve();

function enqueueViewerStartup<T>(operation: () => Promise<T>): Promise<T> {
  const result = viewerStartupTail.catch(() => undefined).then(operation);
  viewerStartupTail = result.then(
    () => undefined,
    () => undefined
  );
  return result;
}

export async function ensureCadViewer(input: {
  workspacePath: string;
  filePath: string;
}): Promise<EnsureCadViewerResult> {
  const target = validateTarget(input);
  if (!target.success) return target;

  const lifecycle = viewerLifecycles.forWorkspace(target.workspacePath);
  const started = await lifecycle.ensureStarted({
    isHealthy: (port) => viewerIsHealthy(port, target.workspacePath),
    start: () => enqueueViewerStartup(() => startViewer(target.workspacePath, lifecycle)),
  });
  return started.success
    ? { success: true, url: buildCadViewerUrl({ ...target, port: started.port }) }
    : started;
}

function validateTarget(input: { workspacePath: string; filePath: string }) {
  const workspacePath = resolve(input.workspacePath);
  const absoluteFilePath = isAbsolute(input.filePath)
    ? input.filePath
    : resolve(workspacePath, input.filePath);
  const relativeFilePath = relative(workspacePath, absoluteFilePath);
  if (!relativeFilePath || relativeFilePath.startsWith('..') || isAbsolute(relativeFilePath)) {
    return { success: false as const, error: 'CAD files must be inside the active workspace.' };
  }
  return { success: true as const, workspacePath, relativeFilePath };
}

export function buildCadViewerUrl(input: {
  workspacePath: string;
  relativeFilePath: string;
  port: number;
}): string {
  // The Viewer serves one directory fixed at launch, so the page is always the
  // bare origin and only the root-relative artifact belongs in the URL.
  const url = new URL(`http://${HOST}:${input.port}`);
  url.pathname = '/';
  url.searchParams.set('file', input.relativeFilePath.split(sep).join('/'));
  return url.toString();
}

export function preferredCadViewerPath(
  filePath: string,
  _exists: (candidate: string) => boolean = existsSync
): string {
  // The accepted STEP is the canonical artifact. A legacy generator beside it
  // never replaces it in the viewer.
  return filePath;
}

async function startViewer(
  cwd: string,
  lifecycle: CadViewerProcessLifecycle
): Promise<StartCadViewerResult> {
  const layout = currentTextToCadLayout();
  if (!layout) {
    return {
      success: false,
      error:
        'Text-to-CAD resources were not found. Run Hardcore from the text-to-cad checkout or set HARDCORE_TEXT_TO_CAD_ROOT.',
    };
  }
  if (!viewerClientIsBuilt(layout)) {
    return {
      success: false,
      error: `The CAD Viewer client is not built at ${layout.viewer.dist}. Run pnpm cad:setup to build apps/viewer.`,
    };
  }

  let python = findCadPythonExecutable(layout);
  if (!python) {
    try {
      await provisionCadRuntime();
    } catch (error) {
      return {
        success: false,
        error: `Could not prepare the CAD environment: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
    python = findCadPythonExecutable(layout);
    if (!python) return { success: false, error: 'The CAD Python environment is incomplete.' };
  }

  // The served directory is the cwd, full stop: the launcher takes no
  // directory flag, picks the first free port from 3245 upward, and answers
  // one JSON line once the socket is bound and the app attached.
  let stdout = '';
  let stderr = '';
  const viewerProcess = spawn(
    python,
    ['-m', layout.viewer.launcher, '--host', HOST, '--json', '--dist', layout.viewer.dist],
    {
      cwd,
      env: cadToolEnvironment(),
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );
  let exited = false;
  let spawnError: Error | null = null;
  const viewerChild: CadViewerChild = {
    kill: () => viewerProcess.kill(),
    onTerminated: (listener) => {
      viewerProcess.once('exit', listener);
      viewerProcess.once('error', listener);
    },
  };
  lifecycle.adopt(viewerChild);
  viewerProcess.stdout?.on('data', (chunk: Buffer | string) => {
    stdout = `${stdout}${String(chunk)}`.slice(-16_000);
  });
  viewerProcess.stderr?.on('data', (chunk: Buffer | string) => {
    stderr = `${stderr}${String(chunk)}`.slice(-8_000);
  });
  viewerProcess.once('exit', () => {
    exited = true;
  });
  viewerProcess.once('error', (error) => {
    spawnError = error;
    exited = true;
  });

  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  let launch: CadViewerLaunch | null = null;
  while (Date.now() < deadline) {
    launch = parseCadViewerLaunch(stdout);
    if (launch) break;
    if (spawnError) break;
    if (exited) break;
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  if (!launch) {
    lifecycle.stop(viewerChild);
    const detail = spawnError
      ? (spawnError as Error).message
      : `${stderr.trim()}\n${stdout.trim()}`.trim();
    return {
      success: false,
      error: `CAD Viewer did not start.${detail ? ` ${detail}` : ''}`,
    };
  }

  log.info({ cwd, url: launch.url, action: launch.action }, 'cad: viewer launched');
  if (launch.action === 'reused') {
    // Another launch (this app earlier, or an agent session) already serves
    // this directory with the same code. The launcher process exits on its
    // own; the resident instance is not ours to stop.
    lifecycle.markExternal(launch.port);
  } else if (!lifecycle.markReady(viewerChild, launch.port)) {
    return { success: false, error: 'CAD Viewer startup was replaced by a newer request.' };
  }

  while (Date.now() < deadline) {
    if (await viewerIsHealthy(launch.port, cwd)) return { success: true, port: launch.port };
    if (launch.action === 'started' && !lifecycle.owns(viewerChild)) break;
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));
  }
  lifecycle.stop(viewerChild);
  return {
    success: false,
    error: `CAD Viewer at ${launch.url} did not answer for ${cwd}.${stderr.trim() ? ` ${stderr.trim()}` : ''}`,
  };
}

async function viewerIsHealthy(port: number, workspacePath: string): Promise<boolean> {
  try {
    const response = await fetch(`http://${HOST}:${port}/__cad/server`, {
      signal: AbortSignal.timeout(750),
    });
    if (!response.ok) return false;
    const payload: unknown = await response.json();
    return (
      typeof payload === 'object' &&
      payload !== null &&
      'rootPath' in payload &&
      typeof payload.rootPath === 'string' &&
      resolve(payload.rootPath) === resolve(workspacePath)
    );
  } catch {
    return false;
  }
}

// Re-exported for callers that still resolve the interpreter through the viewer
// service; the runtime service owns the rule.
export { findCadPythonExecutable } from '@main/host/cad/cad-runtime-service';

process.once('exit', () => {
  viewerLifecycles.stopAll();
});
