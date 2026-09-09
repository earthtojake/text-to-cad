import { execFileSync, spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { basename, delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseClaudePluginVersion,
  parseCodexPluginRoot,
  pythonImportsRepositoryCadgen,
  pythonExecutable,
  resolveCadRuntimeRoot,
  resolveCommand,
  resolveDevelopmentPython,
  resolveTextToCadRoot,
  resolveViewerRuntime,
} from './setup-cad.mjs';

/**
 * The desktop's CAD integration gate, run from apps/desktop:
 *
 * 1. `setup-cad.mjs --check` reports the runtime, viewer client, and plugins.
 * 2. Jake's selected cadgen suites run from the canonical tree with the same
 *    interpreter the desktop uses.
 * 3. The canonical viewer launch smoke runs the current cadgen.viewer backend
 *    against the same client build the desktop serves.
 * 4. A plain @step recipe is built, validated, and inspected exactly the way
 *    the desktop does it: `python model.py --json`, then the cadgen doors.
 */
const PROJECT_ROOT = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const TEXT_TO_CAD_ROOT = resolveTextToCadRoot(PROJECT_ROOT);
const CAD_RUNTIME_ROOT = resolveCadRuntimeRoot(PROJECT_ROOT);

function capture(command, args) {
  return execFileSync(resolveCommand(command), args, { encoding: 'utf8' });
}

function run(label, command, args, options = {}) {
  console.log(`\n==> ${label}`);
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? PROJECT_ROOT,
    env: {
      ...process.env,
      PATH: [dirname(process.execPath), process.env.PATH].filter(Boolean).join(delimiter),
      ...options.env,
    },
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${label} failed with status ${result.status}`);
}

function resolvePython() {
  const override = process.env.HARDCORE_CAD_PYTHON?.trim();
  if (override && existsSync(override)) return override;
  const development = resolveDevelopmentPython(TEXT_TO_CAD_ROOT);
  if (development && pythonImportsRepositoryCadgen(development, TEXT_TO_CAD_ROOT)) {
    return development;
  }
  const managed = pythonExecutable(join(CAD_RUNTIME_ROOT, 'venv'));
  if (existsSync(managed)) return managed;
  throw new Error('CAD Python runtime is missing; run pnpm cad:setup');
}

function installedProviders() {
  const codexOutput = capture('codex', ['plugin', 'list']);
  const claudeOutput = capture('claude', ['plugin', 'list']);
  const claudeVersion = parseClaudePluginVersion(claudeOutput);
  return [
    { name: 'Codex', root: parseCodexPluginRoot(codexOutput) },
    {
      name: 'Claude Code',
      root: claudeVersion
        ? join(homedir(), '.claude', 'plugins', 'cache', 'text-to-cad', 'cad', claudeVersion)
        : null,
    },
  ];
}

function main() {
  if (!TEXT_TO_CAD_ROOT) throw new Error('Text-to-CAD resources were not found above apps/desktop');
  run('CAD integration health check', process.execPath, [
    join(PROJECT_ROOT, 'tooling/scripts/setup-cad.mjs'),
    '--check',
  ]);

  const python = resolvePython();
  const providers = installedProviders();
  for (const provider of providers) {
    if (!provider.root || !existsSync(provider.root)) {
      throw new Error(`${provider.name} CAD plugin root was not found`);
    }
  }

  run("Jake's selected cadgen suites (canonical tree)", python, [
    join(PROJECT_ROOT, 'tooling/scripts/run-jake-cad-tests.py'),
    '--tests-root',
    TEXT_TO_CAD_ROOT,
  ]);

  const viewer = resolveViewerRuntime(TEXT_TO_CAD_ROOT);
  if (!viewer) throw new Error('The canonical cadgen viewer is missing');
  run(
    'Viewer launch and import smoke (canonical cadgen)',
    'bash',
    [join(TEXT_TO_CAD_ROOT, 'scripts/test/test-viewer-launch.sh')],
    { cwd: TEXT_TO_CAD_ROOT, env: { VIEWER_RUNTIME_DIR: viewer.dist, VIEWER_PYTHON: python } }
  );

  const scratch = mkdtempSync(join(tmpdir(), 'hardcore-cad-'));
  try {
    const source = join(scratch, basename('emdash-smoke.py'));
    const step = join(scratch, 'emdash-smoke.step');
    copyFileSync(join(PROJECT_ROOT, 'tooling/fixtures/cad/emdash-smoke.py'), source);

    run(
      'cadgen 0.5 script door: build a real STEP artifact',
      python,
      [basename(source), '--json'],
      { cwd: scratch }
    );
    if (!existsSync(step)) throw new Error(`the recipe did not write ${step}`);

    run(
      'cadgen 0.5 doors: validate the generated STEP artifact',
      python,
      ['-m', 'cadgen.cli', 'step', 'inspect', 'validate', basename(step)],
      { cwd: scratch }
    );
    run(
      'cadgen 0.5 doors: inspect topology and bounds',
      python,
      ['-m', 'cadgen.cli', 'step', 'inspect', 'refs', basename(step), '--facts'],
      { cwd: scratch }
    );
    console.log(`\nCAD artifact passed: ${step}`);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
