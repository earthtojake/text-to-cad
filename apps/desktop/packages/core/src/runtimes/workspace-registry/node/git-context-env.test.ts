import { chmod, mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createRegistryGitContext } from './git-context';

let temporaryDirectory: string | undefined;

afterEach(async () => {
  if (temporaryDirectory) await rm(temporaryDirectory, { recursive: true, force: true });
  temporaryDirectory = undefined;
});

describe('createRegistryGitContext environment', () => {
  it('loads the current environment and composes non-interactive overrides per spawn', async () => {
    temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), 'emdash-registry-git-env-'));
    const binDirectory = path.join(temporaryDirectory, 'bin');
    await mkdir(binDirectory);
    await writeFile(
      path.join(binDirectory, 'git'),
      '#!/bin/sh\nprintf "%s|%s|%s" "$EMDASH_ENV_REVISION" "$LC_ALL" "$GIT_TERMINAL_PROMPT"\n'
    );
    await chmod(path.join(binDirectory, 'git'), 0o755);
    let env = { PATH: binDirectory, EMDASH_ENV_REVISION: 'before-refresh' };
    const git = createRegistryGitContext({ env: async () => env });

    const before = await git.exec(temporaryDirectory).exec(['version']);
    env = { PATH: binDirectory, EMDASH_ENV_REVISION: 'after-refresh' };
    const after = await git.exec(temporaryDirectory).exec(['version']);

    expect(before.stdout).toBe('before-refresh|C|0');
    expect(after.stdout).toBe('after-refresh|C|0');
  });
});
