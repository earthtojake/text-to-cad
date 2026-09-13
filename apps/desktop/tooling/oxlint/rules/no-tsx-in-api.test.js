import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { DEFAULT_DESKTOP_CORE_SRC_ROOT, isTsxInApiFile } from './no-tsx-in-api.js';

const repoRoot = path.resolve(import.meta.dirname, '../../..');

test('classifies tsx files under feature api surfaces', () => {
  const root = DEFAULT_DESKTOP_CORE_SRC_ROOT;
  assert.equal(isTsxInApiFile(path.join(root, 'features/tasks/api/view.tsx')), true);
  assert.equal(isTsxInApiFile(path.join(root, 'features/tasks/api/browser/nested/view.tsx')), true);
  assert.equal(isTsxInApiFile(path.join(root, 'features/tasks/api/client.ts')), false);
  assert.equal(isTsxInApiFile(path.join(root, 'features/tasks/browser/view.tsx')), false);
  assert.equal(isTsxInApiFile(path.join(root, 'features/tasks/api.tsx')), false);
  assert.equal(isTsxInApiFile(path.join(root, 'primitives/tasks/api/view.tsx')), false);
  assert.equal(isTsxInApiFile('/elsewhere/src/core/features/tasks/api/view.tsx'), false);
  assert.equal(isTsxInApiFile(''), false);
});

test('classifies against a custom core src root', () => {
  assert.equal(isTsxInApiFile('/tmp/x/src/core/features/a/api/view.tsx', '/tmp/x/src/core'), true);
  assert.equal(
    isTsxInApiFile('/tmp/x/src/core/features/a/browser/view.tsx', '/tmp/x/src/core'),
    false
  );
});

test('reports tsx files in api surfaces once and respects allowlists', async () => {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'emdash-no-tsx-in-api-'));
  try {
    const coreRoot = path.join(tempRoot, 'src/core');
    const violatingPath = path.join(coreRoot, 'features/tasks/api/browser/task-badge.tsx');
    const allowlistedPath = path.join(coreRoot, 'features/projects/api/project-badge.tsx');
    const browserPath = path.join(coreRoot, 'features/tasks/browser/task-badge.tsx');
    const allowlistPath = path.join(tempRoot, 'allowlists.json');
    const configPath = path.join(tempRoot, '.oxlintrc.json');

    await mkdir(path.dirname(violatingPath), { recursive: true });
    await mkdir(path.dirname(allowlistedPath), { recursive: true });
    await mkdir(path.dirname(browserPath), { recursive: true });
    await writeFile(
      allowlistPath,
      JSON.stringify({ tsxInApi: [path.relative(tempRoot, allowlistedPath)] })
    );
    await writeFile(
      configPath,
      JSON.stringify({
        plugins: ['eslint', 'typescript'],
        jsPlugins: [path.join(repoRoot, 'tooling/oxlint/index.js')],
        env: { browser: true, es2020: true },
        rules: {
          'emdash/no-tsx-in-api': [
            'error',
            {
              allowlistPath,
              repoRoot: tempRoot,
              coreSrcRoot: coreRoot,
            },
          ],
        },
      })
    );
    const component = 'export const Badge = () => <span>badge</span>;\n';
    await writeFile(violatingPath, component);
    await writeFile(allowlistedPath, component);
    await writeFile(browserPath, component);

    const violatingResult = await runOxlint(configPath, violatingPath);
    assert.notEqual(violatingResult.code, 0);
    assert.match(violatingResult.output, /emdash\(no-tsx-in-api\)/);
    assert.match(violatingResult.output, /React components belong in browser\//);
    assert.equal(violatingResult.output.match(/emdash\(no-tsx-in-api\)/g).length, 1);

    const allowlistedResult = await runOxlint(configPath, allowlistedPath);
    assert.equal(allowlistedResult.code, 0, allowlistedResult.output);

    const browserResult = await runOxlint(configPath, browserPath);
    assert.equal(browserResult.code, 0, browserResult.output);
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
