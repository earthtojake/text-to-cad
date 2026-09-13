import { execFile } from 'node:child_process';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import { hostPath } from '#runtimes/git/node/testing/paths';
import { createBoundExec } from '#services/exec/api';
import { CanonicalGitIdentityResolver } from './identity-resolver';

const execFileAsync = promisify(execFile);

async function makeRepo(): Promise<string> {
  const repo = await mkdtemp(path.join(tmpdir(), 'emdash-git-identity-'));
  await execFileAsync('git', ['init', '-b', 'main'], { cwd: repo });
  await execFileAsync('git', ['config', 'user.email', 'test@example.com'], { cwd: repo });
  await execFileAsync('git', ['config', 'user.name', 'Test User'], { cwd: repo });
  await writeFile(path.join(repo, 'README.md'), 'initial\n', 'utf8');
  await execFileAsync('git', ['add', 'README.md'], { cwd: repo });
  await execFileAsync('git', ['commit', '-m', 'initial'], { cwd: repo });
  return realpath(repo);
}

describe('CanonicalGitIdentityResolver', () => {
  it('shares repository identity while distinguishing linked checkouts', async () => {
    const repo = await makeRepo();
    const linked = await mkdtemp(path.join(tmpdir(), 'emdash-git-linked-'));
    await execFileAsync('git', ['worktree', 'add', linked, '-b', 'linked'], { cwd: repo });
    const resolver = new CanonicalGitIdentityResolver({
      exec: createBoundExec({ file: 'git', cwd: process.cwd(), env: process.env }),
    });

    try {
      const [mainResult, linkedResult] = await Promise.all([
        resolver.resolve({ checkout: hostPath(repo) }),
        resolver.resolve({ checkout: hostPath(linked) }),
      ]);
      expect(mainResult.success).toBe(true);
      expect(linkedResult.success).toBe(true);
      if (!mainResult.success || !linkedResult.success) return;

      expect(linkedResult.data.repositoryId).toBe(mainResult.data.repositoryId);
      expect(linkedResult.data.objectStoreId).toBe(mainResult.data.objectStoreId);
      expect(linkedResult.data.checkoutId).not.toBe(mainResult.data.checkoutId);
      expect(linkedResult.data.checkoutRoot).toBe(await realpath(linked));
    } finally {
      resolver.dispose();
    }
  });

  it('shares concurrent alias resolution and retries failures', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'emdash-git-identity-retry-'));
    const resolver = new CanonicalGitIdentityResolver({
      exec: createBoundExec({ file: 'git', cwd: process.cwd(), env: process.env }),
    });
    const selector = { checkout: hostPath(directory) } as const;

    try {
      const [first, second] = await Promise.all([
        resolver.resolve(selector),
        resolver.resolve(selector),
      ]);
      expect(first.success).toBe(false);
      expect(second).toBe(first);

      await execFileAsync('git', ['init', '-b', 'main'], { cwd: directory });
      await expect(resolver.resolve(selector)).resolves.toMatchObject({ success: true });
    } finally {
      resolver.dispose();
    }
  });
});
