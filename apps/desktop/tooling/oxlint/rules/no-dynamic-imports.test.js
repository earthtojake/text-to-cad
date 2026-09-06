import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const repoRoot = path.resolve(import.meta.dirname, '../../..');

test('reports dynamic imports and allows static imports', async () => {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'emdash-no-dynamic-imports-'));
  try {
    const configPath = path.join(tempRoot, '.oxlintrc.json');
    await writeFile(
      configPath,
      JSON.stringify({
        plugins: ['eslint', 'typescript'],
        jsPlugins: [path.join(repoRoot, 'tooling/oxlint/index.js')],
        env: { node: true, es2020: true },
        rules: { 'emdash/no-dynamic-imports': 'error' },
      })
    );

    const invalidPath = path.join(tempRoot, 'invalid.ts');
    await writeFile(invalidPath, "await import('./dependency.js');\n");
    const invalidResult = await runOxlint(configPath, invalidPath);
    assert.notEqual(invalidResult.code, 0);
    assert.match(invalidResult.output, /emdash\(no-dynamic-imports\)/);

    const validPath = path.join(tempRoot, 'valid.ts');
    await writeFile(validPath, "import './dependency.js';\n");
    const validResult = await runOxlint(configPath, validPath);
    assert.equal(validResult.code, 0, validResult.output);
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
