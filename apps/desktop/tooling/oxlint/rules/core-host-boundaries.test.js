import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { isCoreHostSpecifier, isMainCoreFeatureSpecifier } from './core-host-boundaries.js';

const repoRoot = path.resolve(import.meta.dirname, '../../..');

test('classifies forbidden host and feature imports', () => {
  assert.equal(isCoreHostSpecifier('@main/lib/logger'), true);
  assert.equal(isCoreHostSpecifier('@renderer/lib/ui/button'), true);
  assert.equal(isCoreHostSpecifier('@emdash/shared/logger'), false);
  assert.equal(isMainCoreFeatureSpecifier('@core/features/tasks/node'), true);
  assert.equal(isMainCoreFeatureSpecifier('@core/primitives/tasks/api'), false);
});

test('reports both process-direction boundaries and respects generated allowlists', async () => {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'emdash-core-host-boundaries-'));
  try {
    const coreRoot = path.join(tempRoot, 'src/core');
    const mainCoreRoot = path.join(tempRoot, 'src/main/core');
    const corePath = path.join(coreRoot, 'features/tasks/node/controller.ts');
    const mainCorePath = path.join(mainCoreRoot, 'tasks/task-service.ts');
    const allowlistedPath = path.join(coreRoot, 'features/projects/node/controller.ts');
    const allowlistPath = path.join(tempRoot, 'allowlists.json');
    const configPath = path.join(tempRoot, '.oxlintrc.json');

    await mkdir(path.dirname(corePath), { recursive: true });
    await mkdir(path.dirname(mainCorePath), { recursive: true });
    await mkdir(path.dirname(allowlistedPath), { recursive: true });
    await writeFile(
      allowlistPath,
      JSON.stringify({
        coreToHost: [path.relative(tempRoot, allowlistedPath)],
        mainCoreToFeatures: [],
        crossSlice: [],
      })
    );
    await writeFile(
      configPath,
      JSON.stringify({
        plugins: ['eslint', 'typescript'],
        jsPlugins: [path.join(repoRoot, 'tooling/oxlint/index.js')],
        env: { node: true, es2020: true },
        rules: {
          'emdash/core-host-boundaries': [
            'error',
            {
              allowlistPath,
              repoRoot: tempRoot,
              coreSrcRoot: coreRoot,
              mainCoreSrcRoot: mainCoreRoot,
            },
          ],
        },
      })
    );
    await writeFile(
      corePath,
      [
        "import { logger } from '@main/lib/logger';",
        "export { appState } from '@renderer/lib/stores/app-state';",
        "await import('@main/host/window');",
      ].join('\n')
    );
    await writeFile(
      mainCorePath,
      [
        "import { taskEvents } from '@core/features/tasks/node/events';",
        "export { projectEvents } from '@core/features/projects/node/events';",
        "await import('@core/features/workspaces/node/events');",
      ].join('\n')
    );
    await writeFile(allowlistedPath, "import { logger } from '@main/lib/logger';\n");

    const coreResult = await runOxlint(configPath, corePath);
    assert.notEqual(coreResult.code, 0);
    assert.match(coreResult.output, /emdash\(core-host-boundaries\)/);
    assert.match(coreResult.output, /@main\/lib\/logger/);
    assert.match(coreResult.output, /@renderer\/lib\/stores\/app-state/);
    assert.match(coreResult.output, /@main\/host\/window/);

    const mainResult = await runOxlint(configPath, mainCorePath);
    assert.notEqual(mainResult.code, 0);
    assert.match(mainResult.output, /@core\/features\/tasks\/node\/events/);
    assert.match(mainResult.output, /@core\/features\/projects\/node\/events/);
    assert.match(mainResult.output, /@core\/features\/workspaces\/node\/events/);

    const allowlistedResult = await runOxlint(configPath, allowlistedPath);
    assert.equal(allowlistedResult.code, 0, allowlistedResult.output);
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

test('missing coreToHost key and missing allowlist file both mean no exceptions', async () => {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'emdash-core-host-boundaries-strict-'));
  try {
    const coreRoot = path.join(tempRoot, 'src/core');
    const corePath = path.join(coreRoot, 'features/tasks/node/controller.ts');
    const allowlistPath = path.join(tempRoot, 'allowlists.json');
    const configPath = path.join(tempRoot, '.oxlintrc.json');

    await mkdir(path.dirname(corePath), { recursive: true });
    await writeFile(corePath, "import { logger } from '@main/lib/logger';\n");
    await writeFile(
      configPath,
      JSON.stringify({
        plugins: ['eslint', 'typescript'],
        jsPlugins: [path.join(repoRoot, 'tooling/oxlint/index.js')],
        env: { node: true, es2020: true },
        rules: {
          'emdash/core-host-boundaries': [
            'error',
            {
              allowlistPath,
              repoRoot: tempRoot,
              coreSrcRoot: coreRoot,
              mainCoreSrcRoot: path.join(tempRoot, 'src/main/core'),
            },
          ],
        },
      })
    );

    // Allowlist file present but without a coreToHost key: hard error.
    await writeFile(allowlistPath, JSON.stringify({ crossSlice: [] }));
    const missingKeyResult = await runOxlint(configPath, corePath);
    assert.notEqual(missingKeyResult.code, 0);
    assert.match(missingKeyResult.output, /@main\/lib\/logger/);

    // Allowlist file deleted entirely: still a hard error (ENOENT -> no exceptions).
    await rm(allowlistPath);
    const missingFileResult = await runOxlint(configPath, corePath);
    assert.notEqual(missingFileResult.code, 0);
    assert.match(missingFileResult.output, /@main\/lib\/logger/);
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

function runOxlint(config, file) {
  return new Promise((resolve, reject) => {
    const child = spawn('pnpm', ['exec', 'oxlint', '--config', config, file], {
      cwd: repoRoot,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    child.stdout.on('data', (chunk) => {
      output += chunk;
    });
    child.stderr.on('data', (chunk) => {
      output += chunk;
    });
    child.on('error', reject);
    child.on('close', (code) => resolve({ code, output }));
  });
}
