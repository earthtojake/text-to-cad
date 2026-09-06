import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  CAD_RUNTIME_CONSTRAINTS_PATH,
  CAD_SKILL_PACKAGE,
  bootstrapPythonCandidates,
  bootstrapPythonCommand,
  bundledPluginSignature,
  cadRuntimeInstallPlan,
  compareVersions,
  hasMarketplace,
  hasMarketplaceRoot,
  hasPlugin,
  isTextToCadRoot,
  managedRuntimeTransactionPaths,
  parseClaudePluginVersion,
  parseCodexPluginRoot,
  parseCodexPluginVersion,
  parseCadRuntimeConstraints,
  parseOptions,
  parseVersion,
  providerPluginInstallPlan,
  provisionManagedPythonEnvironment,
  readTextToCadVersion,
  recoverManagedPythonEnvironment,
  resolveBootstrapPython,
  resolveCadRuntimeRoot,
  resolveCommand,
  resolveDevelopmentPython,
  resolveStagedPluginRoot,
  resolveTextToCadRoot,
  resolveViewerRuntime,
  shouldShipBundledPluginPath,
  stageBundledPlugin,
  stagedPluginIsCurrent,
} from './setup-cad.mjs';

const REPOSITORY_ROOT = new URL('../../../..', import.meta.url).pathname.replace(/\/$/, '');

test('runs the setup entry point through a symlink', () => {
  const scratch = mkdtempSync(join(tmpdir(), 'hardcore-setup-entry-'));
  try {
    const entry = join(scratch, 'setup.mjs');
    symlinkSync(new URL('./setup-cad.mjs', import.meta.url), entry);
    const result = spawnSync(process.execPath, [entry, '--provider=invalid'], {
      encoding: 'utf8',
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /--provider must be all, codex, or claude/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

function writeTextToCadFixture(root, { viewerAsSymlink = true } = {}) {
  mkdirSync(join(root, '.codex-plugin'), { recursive: true });
  mkdirSync(join(root, '.claude-plugin'), { recursive: true });
  mkdirSync(join(root, 'packages', 'cadgen'), { recursive: true });
  mkdirSync(join(root, 'skills', 'cad', '__pycache__'), { recursive: true });
  mkdirSync(join(root, 'skills', 'cad-viewer', 'scripts'), { recursive: true });
  mkdirSync(join(root, 'packages', 'cadgen', 'src', 'cadgen', 'viewer'), { recursive: true });
  mkdirSync(join(root, 'apps', 'viewer', 'dist'), { recursive: true });
  mkdirSync(join(root, 'apps', 'viewer', 'src'), { recursive: true });
  mkdirSync(join(root, 'apps', 'viewer', 'node_modules', 'vite'), { recursive: true });
  mkdirSync(join(root, 'apps', 'viewer', 'tests_server'), { recursive: true });
  writeFileSync(join(root, 'VERSION'), '0.4.28\n');
  writeFileSync(join(root, 'LICENSE'), 'MIT');
  writeFileSync(join(root, '.codex-plugin', 'plugin.json'), '{}');
  writeFileSync(join(root, '.claude-plugin', 'plugin.json'), '{}');
  writeFileSync(join(root, 'packages', 'cadgen', 'pyproject.toml'), '[project]\nname = "cadgen"\n');
  writeFileSync(join(root, 'skills', 'cad', 'SKILL.md'), 'CAD');
  writeFileSync(join(root, 'skills', 'cad', '__pycache__', 'runtime.pyc'), 'cache');
  writeFileSync(join(root, 'skills', 'cad-viewer', 'SKILL.md'), 'VIEWER');
  writeFileSync(
    join(root, 'packages', 'cadgen', 'src', 'cadgen', 'viewer', '__main__.py'),
    'print("viewer")'
  );
  writeFileSync(join(root, 'apps', 'viewer', 'dist', 'index.html'), '<html></html>');
  writeFileSync(join(root, 'apps', 'viewer', 'dist', 'index.js.map'), '{}');
  writeFileSync(join(root, 'apps', 'viewer', 'src', 'App.js'), 'source');
  writeFileSync(join(root, 'apps', 'viewer', 'package.json'), '{"name":"cad-viewer"}');
  writeFileSync(join(root, 'apps', 'viewer', 'requirements.txt'), 'cadgen>=0.4.29');
  writeFileSync(join(root, 'apps', 'viewer', 'node_modules', 'vite', 'index.js'), 'dep');
  writeFileSync(join(root, 'apps', 'viewer', 'tests_server', 'test_x.py'), 'test');
  if (viewerAsSymlink) {
    symlinkSync(
      '../../../apps/viewer',
      join(root, 'skills', 'cad-viewer', 'scripts', 'viewer'),
      'dir'
    );
  }
}

test('installs the canonical CAD plugin into both supported agents', () => {
  assert.deepEqual(CAD_SKILL_PACKAGE, {
    marketplace: 'text-to-cad',
    plugin: 'cad@text-to-cad',
    delivery: 'provider-plugin',
  });
  assert.deepEqual(providerPluginInstallPlan('codex', '/Applications/Hardcore/CAD'), [
    ['plugin', 'marketplace', 'add', '/Applications/Hardcore/CAD'],
    ['plugin', 'add', 'cad@text-to-cad'],
  ]);
  assert.deepEqual(providerPluginInstallPlan('claude', '/Applications/Hardcore/CAD'), [
    ['plugin', 'marketplace', 'add', '/Applications/Hardcore/CAD'],
    ['plugin', 'install', 'cad@text-to-cad'],
  ]);
  assert.throws(() => providerPluginInstallPlan('other'), /Unsupported CAD skill provider/);
});

test('finds the Text-to-CAD tree above apps/desktop and honors an explicit root', () => {
  assert.equal(isTextToCadRoot(REPOSITORY_ROOT), true);
  assert.equal(resolveTextToCadRoot(join(REPOSITORY_ROOT, 'apps', 'desktop'), {}), REPOSITORY_ROOT);
  assert.equal(
    readTextToCadVersion(REPOSITORY_ROOT),
    readFileSync(join(REPOSITORY_ROOT, 'VERSION'), 'utf8').trim()
  );
  assert.equal(resolveTextToCadRoot('/tmp/missing-desktop-root', {}), null);
  assert.equal(
    resolveTextToCadRoot('/tmp/missing-desktop-root', {
      HARDCORE_TEXT_TO_CAD_ROOT: REPOSITORY_ROOT,
    }),
    REPOSITORY_ROOT
  );
});

test('prefers the editable viewer app in a checkout and the bundled cadgen client otherwise', (context) => {
  const root = mkdtempSync(join(tmpdir(), 'hardcore-text-to-cad-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  writeTextToCadFixture(root);
  assert.deepEqual(resolveViewerRuntime(root), {
    kind: 'repository',
    root: join(root, 'apps', 'viewer'),
    launcher: 'cadgen.viewer',
    dist: join(root, 'apps', 'viewer', 'dist'),
  });

  const bundle = mkdtempSync(join(tmpdir(), 'hardcore-text-to-cad-bundle-'));
  context.after(() => rmSync(bundle, { recursive: true, force: true }));
  const runtime = join(bundle, 'packages', 'cadgen', 'src', 'cadgen');
  mkdirSync(join(runtime, 'viewer'), { recursive: true });
  mkdirSync(join(runtime, '_runtime', 'viewer'), { recursive: true });
  writeFileSync(join(runtime, 'viewer', '__main__.py'), '');
  writeFileSync(join(runtime, '_runtime', 'viewer', 'index.html'), '<html></html>');
  assert.equal(resolveViewerRuntime(bundle)?.kind, 'bundle');
  assert.equal(resolveViewerRuntime('/tmp/missing-text-to-cad'), null);
});

test('parses provider CLI versions', () => {
  assert.deepEqual(parseVersion('codex-cli 0.148.0'), [0, 148, 0]);
  assert.deepEqual(parseVersion('2.1.237 (Claude Code)'), [2, 1, 237]);
  assert.equal(parseVersion('unknown'), null);
});

test('compares semantic version tuples', () => {
  assert.equal(compareVersions([0, 148, 0], [0, 142, 0]), 1);
  assert.equal(compareVersions([0, 142, 0], [0, 142, 0]), 0);
  assert.equal(compareVersions([0, 141, 9], [0, 142, 0]), -1);
});

test('locks every installed CAD dependency and carries the lock into build isolation', () => {
  const constraints = parseCadRuntimeConstraints(
    readFileSync(CAD_RUNTIME_CONSTRAINTS_PATH, 'utf8')
  );
  assert.equal(constraints.build123d, '0.11.1');
  assert.equal(constraints['cadquery-ocp'], '7.9.3.1.1');
  assert.equal(constraints.ezdxf, '1.4.4');
  assert.equal(constraints.shapely, '2.1.2');
  // IPython selects colorama only on Windows. Keep that platform-only edge
  // locked too, or the strict runtime health check will reject Windows installs.
  assert.equal(constraints.colorama, '0.4.6');
  assert.equal(constraints.pip, '25.2');
  assert.ok(Object.keys(constraints).length > 40);

  const plan = cadRuntimeInstallPlan('/runtime/python', '/bundle/cadgen', '/bundle/lock.txt');
  assert.deepEqual(plan[0], {
    command: '/runtime/python',
    args: [
      '-m',
      'pip',
      'install',
      '--disable-pip-version-check',
      '--upgrade',
      'pip==25.2',
      'setuptools==80.9.0',
      'wheel==0.45.1',
    ],
  });
  assert.deepEqual(plan[1].args.slice(-3), ['--constraint', '/bundle/lock.txt', '/bundle/cadgen']);
  assert.equal(plan[1].environment.PIP_CONSTRAINT, '/bundle/lock.txt');

  const editable = cadRuntimeInstallPlan('/runtime/python', '/repo/packages/cadgen', '/lock.txt', {
    editable: true,
  });
  assert.deepEqual(editable[1].args.slice(-4), [
    '--constraint',
    '/lock.txt',
    '--editable',
    '/repo/packages/cadgen',
  ]);
});

test('rejects a drifting or ranged CAD runtime constraint', () => {
  assert.throws(
    () => parseCadRuntimeConstraints('build123d>=0.11\n'),
    /Invalid CAD runtime constraint/
  );
});

test('recognizes the marketplace and plugin in provider output', () => {
  assert.equal(hasMarketplace('text-to-cad  /tmp/marketplaces/text-to-cad'), true);
  assert.equal(
    hasMarketplaceRoot('text-to-cad  /Applications/Hardcore/CAD', '/Applications/Hardcore/CAD'),
    true
  );
  assert.equal(
    hasMarketplaceRoot('text-to-cad  /tmp/marketplaces/text-to-cad', '/Applications/Hardcore/CAD'),
    false
  );
  assert.equal(hasPlugin('cad@text-to-cad installed, enabled 0.4.23'), true);
  assert.equal(
    hasPlugin('cad@text-to-cad  not installed           /Applications/Hardcore.app/CAD'),
    false
  );
  assert.equal(
    hasPlugin(`❯ cad@text-to-cad
    Version: 0.4.28
    Scope: user
    Status: ✔ enabled`),
    true
  );
  assert.equal(hasPlugin('unrelated@marketplace'), false);
});

test('finds the installed plugin root and version in provider output', () => {
  assert.equal(
    parseCodexPluginRoot(
      'cad@text-to-cad  installed, enabled  0.4.23  /tmp/marketplaces/text-to-cad  \n'
    ),
    '/tmp/marketplaces/text-to-cad'
  );
  assert.equal(
    parseCodexPluginVersion(
      'cad@text-to-cad  installed, enabled  0.4.25  /tmp/marketplaces/text-to-cad'
    ),
    '0.4.25'
  );
  assert.equal(
    parseClaudePluginVersion('❯ cad@text-to-cad\n    Version: 0.4.23\n    Scope: user'),
    null
  );
  assert.equal(
    parseClaudePluginVersion(
      '❯ cad@text-to-cad\n    Version: 0.4.23\n    Scope: user\n    Status: ✔ enabled'
    ),
    '0.4.23'
  );
  assert.equal(parseClaudePluginVersion('Version: 9.9.9\nno CAD plugin'), null);
  assert.equal(
    parseCodexPluginRoot('cad@text-to-cad  not installed           /Applications/Hardcore.app/CAD'),
    null
  );
  assert.equal(
    parseCodexPluginVersion(
      'cad@text-to-cad  not installed           /Applications/Hardcore.app/CAD'
    ),
    null
  );
});

test('ships only the plugin manifests, skills, and the viewer runtime', () => {
  const root = '/repo';
  assert.equal(shouldShipBundledPluginPath(root, '/repo/skills/cad/SKILL.md'), true);
  assert.equal(shouldShipBundledPluginPath(root, '/repo/.codex-plugin/plugin.json'), true);
  assert.equal(shouldShipBundledPluginPath(root, '/repo/VERSION'), true);
  assert.equal(shouldShipBundledPluginPath(root, '/repo/packages/cadgen/pyproject.toml'), false);
  assert.equal(shouldShipBundledPluginPath(root, '/repo/apps/viewer/dist/index.html'), false);
  assert.equal(shouldShipBundledPluginPath(root, '/repo/skills/cad/__pycache__/x.pyc'), false);
  assert.equal(shouldShipBundledPluginPath(root, '/repo/skills/dxf/scripts/gen.pyc'), false);
  // cad-viewer never ships from the desktop: the app shows models itself and stages cad-desktop instead.
  const viewer = '/repo/skills/cad-viewer/scripts/viewer';
  assert.equal(shouldShipBundledPluginPath(root, '/repo/skills/cad-viewer/SKILL.md'), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/dist/index.html`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/dist/assets/index.js.map`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/server/main.py`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/package.json`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/src/App.js`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/node_modules/vite/index.js`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/tests_server/test_x.py`), false);
  assert.equal(shouldShipBundledPluginPath(root, `${viewer}/vite.config.mjs`), false);
});

test('stages a symlink-free plugin copy with the viewer runtime materialized', (context) => {
  const textToCadRoot = mkdtempSync(join(tmpdir(), 'hardcore-text-to-cad-'));
  const userDataRoot = mkdtempSync(join(tmpdir(), 'hardcore-user-data-'));
  context.after(() => {
    rmSync(textToCadRoot, { recursive: true, force: true });
    rmSync(userDataRoot, { recursive: true, force: true });
  });
  writeTextToCadFixture(textToCadRoot);

  const runtimeRoot = resolveCadRuntimeRoot('/unused', {
    HARDCORE_CAD_RUNTIME_ROOT: join(userDataRoot, 'cad-runtime'),
  });
  // The desktop's own skills ride on top of the plugin; cad-viewer is replaced
  // by cad-desktop because the app shows models itself.
  const overlayRoot = join(userDataRoot, 'desktop-skills');
  mkdirSync(join(overlayRoot, 'cad-desktop'), { recursive: true });
  writeFileSync(join(overlayRoot, 'cad-desktop', 'SKILL.md'), 'DESKTOP');
  const stagedRoot = stageBundledPlugin(textToCadRoot, runtimeRoot, { overlayRoot });

  assert.equal(stagedRoot, resolveStagedPluginRoot(runtimeRoot));
  assert.equal(readFileSync(join(stagedRoot, 'skills', 'cad', 'SKILL.md'), 'utf8'), 'CAD');
  assert.equal(readFileSync(join(stagedRoot, 'VERSION'), 'utf8').trim(), '0.4.28');
  assert.equal(existsSync(join(stagedRoot, 'skills', 'cad', '__pycache__')), false);
  assert.equal(existsSync(join(stagedRoot, 'packages')), false);
  assert.equal(existsSync(join(stagedRoot, 'apps')), false);
  assert.equal(existsSync(join(stagedRoot, 'skills', 'cad-viewer')), false);
  assert.equal(
    readFileSync(join(stagedRoot, 'skills', 'cad-desktop', 'SKILL.md'), 'utf8'),
    'DESKTOP'
  );
  assert.equal(stagedRoot.startsWith(textToCadRoot), false);
  assert.equal(
    stagedPluginIsCurrent(stagedRoot, bundledPluginSignature(textToCadRoot, { overlayRoot })),
    true
  );
  // Without the overlay the signature differs, so a desktop skill edit restages.
  assert.notEqual(
    bundledPluginSignature(textToCadRoot, { overlayRoot }),
    bundledPluginSignature(textToCadRoot, { overlayRoot: null })
  );

  // A changed skill invalidates the staged copy.
  writeFileSync(join(textToCadRoot, 'skills', 'cad', 'SKILL.md'), 'CAD v2');
  stageBundledPlugin(textToCadRoot, runtimeRoot, { overlayRoot });
  assert.equal(
    readFileSync(join(stagedRoot, 'skills', 'cad', 'SKILL.md'), 'utf8').startsWith('CAD'),
    true
  );
});

test('resolves the development CAD runtime locally unless an external root is configured', () => {
  assert.equal(resolveCadRuntimeRoot('/project', {}), join('/project', '.cad-runtime'));
  assert.equal(
    resolveCadRuntimeRoot('/project', { HARDCORE_CAD_RUNTIME_ROOT: '/user-data/cad-runtime' }),
    '/user-data/cad-runtime'
  );
});

test("accepts a checkout's own .venv interpreter when present", (context) => {
  const root = mkdtempSync(join(tmpdir(), 'hardcore-dev-venv-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  assert.equal(resolveDevelopmentPython(root, 'darwin'), null);
  mkdirSync(join(root, '.venv', 'bin'), { recursive: true });
  writeFileSync(join(root, '.venv', 'bin', 'python'), '#!/bin/sh\nexit 0\n');
  chmodSync(join(root, '.venv', 'bin', 'python'), 0o755);
  assert.equal(resolveDevelopmentPython(root, 'darwin'), join(root, '.venv', 'bin', 'python'));
  assert.equal(resolveDevelopmentPython(root, 'win32'), null);
  mkdirSync(join(root, '.venv', 'Scripts'), { recursive: true });
  writeFileSync(join(root, '.venv', 'Scripts', 'python.exe'), 'fixture');
  assert.equal(
    resolveDevelopmentPython(root, 'win32'),
    join(root, '.venv', 'Scripts', 'python.exe')
  );
});

test('commits a verified Python environment without moving its installed path', (context) => {
  if (process.platform === 'win32') return;
  const root = mkdtempSync(join(tmpdir(), 'hardcore-staged-python-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  const runtimeRoot = join(root, 'runtime');

  const executable = provisionManagedPythonEnvironment(
    runtimeRoot,
    (candidate) => {
      const python = join(candidate, 'bin', 'python');
      mkdirSync(join(candidate, 'bin'), { recursive: true });
      writeFileSync(python, '#!/bin/sh\nexit 0\n');
      chmodSync(python, 0o755);
      writeFileSync(join(candidate, 'bin', 'cadgen'), `#!${python}\n`);
    },
    { revision: '0.4.28@/repo/packages/cadgen' }
  );

  const paths = managedRuntimeTransactionPaths(runtimeRoot);
  const generation = realpathSync(paths.runtime);
  const installedPath = readlinkSync(paths.runtime);
  assert.equal(lstatSync(paths.runtime).isSymbolicLink(), true);
  assert.equal(executable, join(paths.runtime, 'bin', 'python'));
  assert.equal(
    readFileSync(join(generation, 'bin', 'cadgen'), 'utf8'),
    `#!${installedPath}/bin/python\n`
  );
  assert.deepEqual(JSON.parse(readFileSync(paths.marker, 'utf8')), {
    revision: '0.4.28@/repo/packages/cadgen',
  });
  assert.equal(existsSync(paths.backup), false);
  assert.equal(existsSync(paths.transaction), false);
});

test('keeps the previous Python environment when candidate preparation fails', (context) => {
  if (process.platform === 'win32') return;
  const root = mkdtempSync(join(tmpdir(), 'hardcore-staged-python-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  const runtimeRoot = join(root, 'runtime');
  const paths = managedRuntimeTransactionPaths(runtimeRoot);
  mkdirSync(join(paths.runtime, 'bin'), { recursive: true });
  writeFileSync(join(paths.runtime, 'bin', 'python'), 'old-python');
  writeFileSync(join(paths.runtime, 'known-good'), 'preserve me');
  writeFileSync(paths.marker, '{"revision":"old"}\n');

  assert.throws(
    () =>
      provisionManagedPythonEnvironment(runtimeRoot, (candidate) => {
        mkdirSync(join(candidate, 'bin'), { recursive: true });
        writeFileSync(join(candidate, 'bin', 'python'), 'new-python');
        throw new Error('network unavailable');
      }),
    /network unavailable/
  );

  assert.equal(readFileSync(join(paths.runtime, 'known-good'), 'utf8'), 'preserve me');
  assert.equal(readFileSync(paths.marker, 'utf8'), '{"revision":"old"}\n');
  assert.equal(existsSync(paths.backup), false);
  assert.equal(existsSync(paths.transaction), false);
  assert.deepEqual(readdirSync(paths.generations), []);
});

test('rolls an interrupted runtime swap back to the known-good environment', (context) => {
  if (process.platform === 'win32') return;
  const root = mkdtempSync(join(tmpdir(), 'hardcore-staged-python-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  const runtimeRoot = join(root, 'runtime');
  const paths = managedRuntimeTransactionPaths(runtimeRoot);
  const candidate = join(paths.generations, 'candidate-interrupted');
  mkdirSync(join(candidate, 'bin'), { recursive: true });
  writeFileSync(join(candidate, 'bin', 'python'), 'new-python');
  mkdirSync(join(paths.backup, 'bin'), { recursive: true });
  writeFileSync(join(paths.backup, 'bin', 'python'), 'old-python');
  writeFileSync(join(paths.backup, 'known-good'), 'preserve me');
  symlinkSync(candidate, paths.runtime, 'dir');
  writeFileSync(paths.marker, '{"revision":"new"}\n');
  writeFileSync(paths.markerBackup, '{"revision":"old"}\n');
  writeFileSync(
    paths.transaction,
    `${JSON.stringify({
      version: 1,
      candidate,
      hadRuntime: true,
      hadMarker: true,
    })}\n`
  );

  recoverManagedPythonEnvironment(runtimeRoot);

  assert.equal(lstatSync(paths.runtime).isSymbolicLink(), false);
  assert.equal(readFileSync(join(paths.runtime, 'known-good'), 'utf8'), 'preserve me');
  assert.equal(readFileSync(paths.marker, 'utf8'), '{"revision":"old"}\n');
  assert.equal(existsSync(candidate), false);
  assert.equal(existsSync(paths.backup), false);
  assert.equal(existsSync(paths.transaction), false);
});

test('parses setup options', () => {
  assert.deepEqual(parseOptions([]), {
    check: false,
    provider: 'all',
    runtimeOnly: false,
    refresh: false,
  });
  assert.deepEqual(parseOptions(['--check', '--provider=codex']), {
    check: true,
    provider: 'codex',
    runtimeOnly: false,
    refresh: false,
  });
  assert.deepEqual(parseOptions(['--runtime-only', '--refresh']), {
    check: false,
    provider: 'all',
    runtimeOnly: true,
    refresh: true,
  });
  assert.throws(() => parseOptions(['--runtime-only', '--provider=codex']), /cannot be combined/);
  assert.throws(() => parseOptions(['--provider=other']), /all, codex, or claude/);
});

test('uses the native Python launcher when bootstrapping the pinned runtime', () => {
  assert.equal(bootstrapPythonCommand('win32', {}), 'py.exe');
  assert.equal(bootstrapPythonCommand('darwin', {}), 'python3.11');
  assert.equal(bootstrapPythonCommand('linux', {}), 'python3.11');
  assert.equal(
    bootstrapPythonCommand('linux', { CAD_DESKTOP_BOOTSTRAP_PYTHON: '/opt/python' }),
    '/opt/python'
  );
  assert.deepEqual(bootstrapPythonCandidates('win32', {}), [
    { command: 'py.exe', args: ['-3.11'] },
    { command: 'python.exe', args: [] },
  ]);
});

test('preflights Python 3.11+ and falls back across native launchers', () => {
  const calls = [];
  const selected = resolveBootstrapPython('win32', {}, (command, args) => {
    calls.push([command, args]);
    return command === 'py.exe'
      ? { available: true, ok: false, output: 'Requested Python version not installed' }
      : { available: true, ok: true, output: '3.12.4\n' };
  });
  assert.deepEqual(selected, { command: 'python.exe', args: [], version: [3, 12, 4] });
  assert.equal(calls[0][0], 'py.exe');
  assert.deepEqual(calls[0][1].slice(0, 1), ['-3.11']);
});

test('reports an actionable preflight error instead of promising automatic Python install', () => {
  assert.throws(
    () =>
      resolveBootstrapPython('linux', {}, () => ({
        available: true,
        ok: true,
        output: '3.10.14\n',
      })),
    /requires Python 3\.11 or newer.*Install Python 3\.11\+/s
  );
});

test('ignores project-local CLI shims when resolving providers', () => {
  const separator = process.platform === 'win32' ? ';' : ':';
  const resolved = resolveCommand(
    'missing-provider',
    [`/project/node_modules/.bin`, `/also/missing`].join(separator)
  );
  assert.equal(
    resolved,
    process.platform === 'win32' ? 'missing-provider.cmd' : 'missing-provider'
  );
});

test('keeps native Windows executables distinct from provider command shims', (context) => {
  const root = mkdtempSync(join(tmpdir(), 'hardcore-windows-commands-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  writeFileSync(join(root, 'python.exe'), 'fixture');
  writeFileSync(join(root, 'codex.cmd'), 'fixture');

  assert.equal(resolveCommand('python.exe', root, 'win32'), join(root, 'python.exe'));
  assert.equal(resolveCommand('codex', root, 'win32'), join(root, 'codex.cmd'));
  assert.equal(
    resolveCommand('C:\\Python311\\python.exe', root, 'win32'),
    'C:\\Python311\\python.exe'
  );
});
