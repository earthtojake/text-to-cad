import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  cadRuntimeProvisioningErrorMessage,
  cadRuntimePluginRoot,
  cadRuntimePythonExecutable,
  findSetupScript,
  resolveCadRuntimeRoot,
} from './cad-runtime-service';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

describe('pinned CAD runtime provisioning', () => {
  it('finds the repository setup script from a nested desktop working directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'hardcore-cad-runtime-'));
    temporaryDirectories.push(root);
    const scripts = join(root, 'tooling', 'scripts');
    const nested = join(root, 'apps', 'desktop');
    await mkdir(scripts, { recursive: true });
    await mkdir(nested, { recursive: true });
    const setup = join(scripts, 'setup-cad.mjs');
    await writeFile(setup, '');

    expect(findSetupScript(nested)).toBe(setup);
  });

  it('finds the bundled setup script in a packaged app resources directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'hardcore-cad-packaged-runtime-'));
    temporaryDirectories.push(root);
    const setup = join(root, 'text-to-cad-desktop', 'tooling', 'scripts', 'setup-cad.mjs');
    await mkdir(join(root, 'text-to-cad-desktop', 'tooling', 'scripts'), { recursive: true });
    await writeFile(setup, '');

    expect(findSetupScript('/Applications/Hardcore.app', root)).toBe(setup);
  });

  it('keeps the mutable CAD runtime under Electron user data, outside app resources', () => {
    const resourcesPath = '/Applications/Hardcore.app/Contents/Resources';
    const userDataPath = '/Users/amy/Library/Application Support/Hardcore';
    const runtimeRoot = resolveCadRuntimeRoot(userDataPath, undefined);

    expect(runtimeRoot).toBe(join(userDataPath, 'cad-runtime'));
    expect(runtimeRoot.startsWith(resourcesPath)).toBe(false);
    expect(cadRuntimePluginRoot(runtimeRoot)).toBe(
      join(userDataPath, 'cad-runtime', 'plugins', 'text-to-cad')
    );
    expect(cadRuntimePythonExecutable(runtimeRoot)).toBe(
      join(
        userDataPath,
        'cad-runtime',
        'venv',
        process.platform === 'win32' ? 'Scripts' : 'bin',
        process.platform === 'win32' ? 'python.exe' : 'python'
      )
    );
  });

  it('honors an explicit runtime root for development and support workflows', () => {
    expect(resolveCadRuntimeRoot('/user-data', '/tmp/hardcore-cad-runtime')).toBe(
      '/tmp/hardcore-cad-runtime'
    );
  });

  it('surfaces the setup preflight instead of a generic child-process failure', () => {
    expect(
      cadRuntimeProvisioningErrorMessage({
        stderr: 'Hardcore CAD requires Python 3.11 or newer. Install Python 3.11+ and retry.\n',
      })
    ).toBe('Hardcore CAD requires Python 3.11 or newer. Install Python 3.11+ and retry.');
    expect(cadRuntimeProvisioningErrorMessage(new Error('fallback message'))).toBe(
      'fallback message'
    );
  });
});
