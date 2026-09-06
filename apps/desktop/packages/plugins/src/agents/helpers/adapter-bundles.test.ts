import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import { adapterAssets } from '../adapter-manifest';
import { adapterAssetFileName } from './adapter-assets';
import { validateAdapterBundleAssets } from './adapter-validation';

const packageDirectory = dirname(fileURLToPath(new URL('../../../package.json', import.meta.url)));
const adapterDirectory = join(packageDirectory, 'dist/adapters');

describe('built adapter bundles', () => {
  beforeAll(() => {
    if (
      adapterAssets.every((asset) =>
        existsSync(join(adapterDirectory, adapterAssetFileName(asset)))
      )
    ) {
      return;
    }

    const result = spawnSync('pnpm', ['exec', 'tsdown'], {
      cwd: packageDirectory,
      stdio: 'inherit',
    });
    if (result.status !== 0) {
      throw new Error(`Failed to build adapter bundles for tests (exit ${result.status})`);
    }
  }, 120_000);

  it('passes size and dependency validation', async () => {
    await expect(
      validateAdapterBundleAssets({ adapterDirectory, assets: adapterAssets })
    ).resolves.toBeUndefined();
  });

  it('boots each adapter from a directory without node_modules', async () => {
    for (const asset of adapterAssets) {
      await expect(smokeAdapter(join(adapterDirectory, adapterAssetFileName(asset)))).resolves.toBe(
        undefined
      );
    }
  }, 20_000);
});

async function smokeAdapter(adapterPath: string): Promise<void> {
  const cwd = await mkdtemp(join(tmpdir(), 'emdash-adapter-smoke-'));
  try {
    await new Promise<void>((resolve, reject) => {
      const child = spawn(process.execPath, [adapterPath], {
        cwd,
        env: {
          ...process.env,
          CLAUDE_CODE_EXECUTABLE: process.execPath,
          CODEX_PATH: process.execPath,
        },
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      let output = '';
      const timeout = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error(`${adapterPath} did not exit after stdin closed. Output:\n${output}`));
      }, 5_000);

      child.stdout.on('data', (chunk) => {
        output += String(chunk);
      });
      child.stderr.on('data', (chunk) => {
        output += String(chunk);
      });
      child.on('error', (error) => {
        clearTimeout(timeout);
        reject(error);
      });
      child.on('close', (code) => {
        clearTimeout(timeout);
        if (code === 0) {
          resolve();
          return;
        }
        reject(new Error(`${adapterPath} exited with code ${code}. Output:\n${output}`));
      });
      child.stdin.end();
    });
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
}
