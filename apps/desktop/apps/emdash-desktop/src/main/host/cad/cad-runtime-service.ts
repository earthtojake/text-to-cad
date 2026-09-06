import { execFile, spawnSync } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, join, parse, sep } from 'node:path';
import { promisify } from 'node:util';
import { app } from 'electron';
import { cadToolEnvironment } from '@main/host/cad/cad-python-environment';
import { prependPathEntries } from '@main/host/cad/cad-runtime-path';
import {
  findTextToCadLayout,
  PACKAGED_DESKTOP_TOOLING_DIRECTORY,
  TEXT_TO_CAD_ROOT_ENV,
  type TextToCadLayout,
} from '@main/host/cad/text-to-cad-layout';

const execFileAsync = promisify(execFile);
let provisioning: Promise<void> | null = null;

/**
 * The canonical Text-to-CAD resources this process runs on: the monorepo root
 * in a checkout, or the bundle beside a packaged app. Resolved on every call
 * so an explicit override or a freshly built viewer is seen immediately.
 */
export function currentTextToCadLayout(): TextToCadLayout | null {
  const startDirectories: string[] = [];
  if (typeof app.getAppPath === 'function') startDirectories.push(app.getAppPath());
  startDirectories.push(process.cwd());
  return findTextToCadLayout({
    resourcesPath: app.isPackaged ? process.resourcesPath : null,
    startDirectories,
  });
}

export async function provisionCadRuntime(): Promise<void> {
  if (provisioning) return provisioning;
  provisioning = runProvisioning().finally(() => {
    provisioning = null;
  });
  return provisioning;
}

export function cadRuntimeProvisioningErrorMessage(error: unknown): string {
  if (error && typeof error === 'object') {
    const stderr = readableProcessOutput('stderr' in error ? error.stderr : null);
    if (stderr) return stderr;
    const stdout = readableProcessOutput('stdout' in error ? error.stdout : null);
    if (stdout) return stdout;
  }
  return error instanceof Error ? error.message : String(error);
}

function readableProcessOutput(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null;
  if (Buffer.isBuffer(value)) return value.toString('utf8').trim() || null;
  return null;
}

async function runProvisioning(): Promise<void> {
  const script = findSetupScript(process.cwd(), app.isPackaged ? process.resourcesPath : undefined);
  if (!script) throw new Error('Hardcore could not locate its CAD environment installer.');
  const layout = currentTextToCadLayout();
  if (!layout) {
    throw new Error(
      `Text-to-CAD resources were not found. Run the desktop from the text-to-cad checkout, or set ${TEXT_TO_CAD_ROOT_ENV}.`
    );
  }
  const runtimeRoot = currentCadRuntimeRoot();
  await execFileAsync(process.execPath, [script], {
    cwd: dirname(dirname(dirname(script))),
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
      HARDCORE_CAD_RUNTIME_ROOT: runtimeRoot,
      [TEXT_TO_CAD_ROOT_ENV]: layout.root,
      PYTHONDONTWRITEBYTECODE: '1',
    },
    timeout: 20 * 60_000,
    maxBuffer: 10 * 1024 * 1024,
  });
}

export function resolveCadRuntimeRoot(
  userDataPath: string,
  configuredRoot = process.env.HARDCORE_CAD_RUNTIME_ROOT
): string {
  const configured = configuredRoot?.trim();
  return configured || join(userDataPath, 'cad-runtime');
}

export function cadRuntimePythonExecutable(runtimeRoot: string): string {
  return join(
    runtimeRoot,
    'venv',
    process.platform === 'win32' ? 'Scripts' : 'bin',
    process.platform === 'win32' ? 'python.exe' : 'python'
  );
}

/** The filtered, symlink-free plugin copy provider CLIs install skills from. */
export function cadRuntimePluginRoot(runtimeRoot: string): string {
  return join(runtimeRoot, 'plugins', 'text-to-cad');
}

export function currentCadRuntimeRoot(): string {
  return resolveCadRuntimeRoot(app.getPath('userData'));
}

export function currentCadRuntimePythonExecutable(): string {
  return cadRuntimePythonExecutable(currentCadRuntimeRoot());
}

/**
 * The interpreter that carries cadgen. An explicit override wins; a checkout's
 * own `.venv` is accepted when it imports cadgen from this repository's
 * packages/cadgen (the CONTRIBUTING setup), and the managed runtime under
 * user data is the packaged default.
 */
export function findCadPythonExecutable(
  layout: TextToCadLayout | null = currentTextToCadLayout()
): string | null {
  const configured = process.env.HARDCORE_CAD_PYTHON?.trim();
  if (configured && existsSync(configured)) return configured;
  if (layout?.kind === 'repository') {
    const developmentPython = developmentPythonExecutable(layout.root);
    if (developmentPython && pythonImportsRepositoryCadgen(developmentPython, layout)) {
      return developmentPython;
    }
  }
  const runtimePython = currentCadRuntimePythonExecutable();
  return existsSync(runtimePython) ? runtimePython : null;
}

export function developmentPythonExecutable(root: string): string | null {
  const python = join(
    root,
    '.venv',
    process.platform === 'win32' ? 'Scripts' : 'bin',
    process.platform === 'win32' ? 'python.exe' : 'python'
  );
  return existsSync(python) ? python : null;
}

const repositoryCadgenProbes = new Map<string, boolean>();

function pythonImportsRepositoryCadgen(python: string, layout: TextToCadLayout): boolean {
  const cached = repositoryCadgenProbes.get(python);
  if (cached !== undefined) return cached;
  let imports = false;
  try {
    const probe = spawnSync(
      python,
      ['-c', 'import cadgen, pathlib; print(pathlib.Path(cadgen.__file__).resolve())'],
      { encoding: 'utf8', env: cadToolEnvironment(), timeout: 30_000 }
    );
    const location = probe.status === 0 ? probe.stdout.trim() : '';
    const expected = realpathSafe(layout.cadgenSource);
    imports = Boolean(location) && (location === expected || location.startsWith(expected + sep));
  } catch {
    imports = false;
  }
  repositoryCadgenProbes.set(python, imports);
  return imports;
}

function realpathSafe(path: string): string {
  try {
    return realpathSync.native(path);
  } catch {
    return path;
  }
}

export function findSetupScript(start: string, resourcesPath?: string): string | null {
  if (resourcesPath) {
    const packaged = join(
      resourcesPath,
      PACKAGED_DESKTOP_TOOLING_DIRECTORY,
      'tooling',
      'scripts',
      'setup-cad.mjs'
    );
    if (existsSync(packaged)) return packaged;
  }
  let current = start;
  const root = parse(current).root;
  while (true) {
    const candidate = join(current, 'tooling', 'scripts', 'setup-cad.mjs');
    if (existsSync(candidate)) return candidate;
    if (current === root) return null;
    current = dirname(current);
  }
}

/**
 * The directory whose `python` and `cadgen` agents and terminals should find
 * first: the checkout venv when running from the repository, else the managed
 * runtime under user data. The managed path is named before it is provisioned,
 * so a session started while the installer runs picks the runtime up the moment
 * the venv lands, without a restart.
 */
export function cadRuntimeBinDirectory(
  layout: TextToCadLayout | null = currentTextToCadLayout()
): string {
  return dirname(findCadPythonExecutable(layout) ?? currentCadRuntimePythonExecutable());
}

/**
 * The login-shell environment every worker spawns from (agents, terminals) with
 * the CAD runtime first on PATH. Without this an agent following the CAD skill
 * finds no cadgen in a fresh project and tries to pip-install its own copy, which
 * fails offline and inside sandboxes and duplicates the runtime the app already
 * provisioned.
 */
export function withCadRuntimeOnPath(env: Record<string, string>): Record<string, string> {
  return prependPathEntries(env, [cadRuntimeBinDirectory()]);
}
