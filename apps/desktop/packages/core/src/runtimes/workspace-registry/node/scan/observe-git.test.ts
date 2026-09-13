import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRegistryGitContext } from '../git-context';
import {
  createRemoteUrlCache,
  createUntrackedLinesCache,
  observeWorkspaceGit,
  observeWorkspaceGitRefs,
} from './observe-git';

const run = promisify(execFile);
const gitContext = createRegistryGitContext();

// Integration tests against a real temp repo: the untracked line-count cache
// must hit on unchanged files (stat-keyed), re-read changed files, respect the
// per-scan byte budget, and evict entries for files that stop being untracked.

let repo: string;

async function git(...args: string[]): Promise<void> {
  await run('git', args, { cwd: repo });
}

beforeEach(async () => {
  repo = await mkdtemp(join(tmpdir(), 'emdash-observe-git-'));
  await git('init');
  await git('config', 'user.email', 'test@example.com');
  await git('config', 'user.name', 'Test');
  await git('config', 'commit.gpgsign', 'false');
  await writeFile(join(repo, 'tracked.txt'), 'tracked\n');
  await git('add', '.');
  await git('commit', '-m', 'init');
});

afterEach(async () => {
  await rm(repo, { recursive: true, force: true });
});

describe('observeWorkspaceGit untracked line counting', () => {
  it('counts untracked lines and fills the stat-keyed cache', async () => {
    await writeFile(join(repo, 'one.txt'), 'a\nb\nc\n');
    await writeFile(join(repo, 'two.txt'), 'x\n');
    const cache = createUntrackedLinesCache();

    const observed = await observeWorkspaceGit(gitContext, repo, undefined, {
      untrackedCache: cache,
    });

    expect(observed?.diffStats).toEqual({ added: 4, deleted: 0 });
    expect(cache.size).toBe(2);
    expect(cache.get('one.txt')?.lines).toBe(3);
  });

  it('serves unchanged files from the cache without re-reading them', async () => {
    await writeFile(join(repo, 'one.txt'), 'a\nb\nc\n');
    const cache = createUntrackedLinesCache();
    await observeWorkspaceGit(gitContext, repo, undefined, { untrackedCache: cache });

    // Poison the cached count: if the rescan re-read the file this sentinel
    // would be overwritten and the total would revert to 3.
    const entry = cache.get('one.txt');
    expect(entry).toBeDefined();
    cache.set('one.txt', { ...entry!, lines: 999 });

    const observed = await observeWorkspaceGit(gitContext, repo, undefined, {
      untrackedCache: cache,
    });
    expect(observed?.diffStats).toEqual({ added: 999, deleted: 0 });
  });

  it('re-reads files whose stat changed', async () => {
    await writeFile(join(repo, 'one.txt'), 'a\nb\nc\n');
    const cache = createUntrackedLinesCache();
    await observeWorkspaceGit(gitContext, repo, undefined, { untrackedCache: cache });

    const entry = cache.get('one.txt');
    cache.set('one.txt', { ...entry!, lines: 999 });
    await writeFile(join(repo, 'one.txt'), 'a\nb\nc\nd\ne\n');

    const observed = await observeWorkspaceGit(gitContext, repo, undefined, {
      untrackedCache: cache,
    });
    expect(observed?.diffStats).toEqual({ added: 5, deleted: 0 });
    expect(cache.get('one.txt')?.lines).toBe(5);
  });

  it('degrades the untracked component to null when the byte budget is exceeded', async () => {
    await writeFile(join(repo, 'big.txt'), 'line\n'.repeat(1_000));
    const observed = await observeWorkspaceGit(gitContext, repo, undefined, {
      untrackedCache: createUntrackedLinesCache(),
      untrackedByteBudget: 100,
    });

    // Tracked diff is empty and the untracked count degraded: no +N inflation.
    expect(observed?.diffStats).toEqual({ added: 0, deleted: 0 });
  });

  it('cached files do not consume the byte budget on later scans', async () => {
    await writeFile(join(repo, 'one.txt'), 'line\n'.repeat(50));
    const cache = createUntrackedLinesCache();
    await observeWorkspaceGit(gitContext, repo, undefined, { untrackedCache: cache });

    // Budget smaller than the file: only viable because the count is cached.
    const observed = await observeWorkspaceGit(gitContext, repo, undefined, {
      untrackedCache: cache,
      untrackedByteBudget: 10,
    });
    expect(observed?.diffStats).toEqual({ added: 50, deleted: 0 });
  });

  it('evicts cache entries for files that are no longer untracked', async () => {
    await writeFile(join(repo, 'one.txt'), 'a\n');
    await writeFile(join(repo, 'two.txt'), 'b\n');
    const cache = createUntrackedLinesCache();
    await observeWorkspaceGit(gitContext, repo, undefined, { untrackedCache: cache });
    expect(cache.size).toBe(2);

    await git('add', 'one.txt');
    await observeWorkspaceGit(gitContext, repo, undefined, { untrackedCache: cache });
    expect([...cache.keys()]).toEqual(['two.txt']);
  });
});

async function headOidOf(cwd: string): Promise<string> {
  const { stdout } = await run('git', ['rev-parse', 'HEAD'], { cwd });
  return stdout.trim();
}

// Raw git facts only (spec: Observation): the observer reports config values and
// OIDs verbatim and never interprets breadcrumbs or ref patterns.

describe('observeWorkspaceGit head OID, upstream identity, and PR breadcrumb', () => {
  beforeEach(async () => {
    await git('branch', '-M', 'main');
  });

  it('reports head OID, upstream identity, and the raw breadcrumb', async () => {
    await git('remote', 'add', 'origin', 'https://example.com/acme/app.git');
    await git('config', 'branch.main.remote', 'origin');
    await git('config', 'branch.main.merge', 'refs/heads/main');
    await git('config', 'branch.main.emdash-pr-url', 'https://github.com/acme/app/pull/7');

    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.headOid).toBe(await headOidOf(repo));
    expect(observed?.upstream).toEqual({
      remote: 'origin',
      mergeRef: 'refs/heads/main',
      remoteUrl: 'https://example.com/acme/app.git',
    });
    expect(observed?.prBreadcrumb).toBe('https://github.com/acme/app/pull/7');
  });

  it('reports upstream null without tracking config while other fields populate', async () => {
    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.branch).toBe('main');
    expect(observed?.headOid).toBe(await headOidOf(repo));
    expect(observed?.upstream).toBeNull();
    expect(observed?.prBreadcrumb).toBeNull();
  });

  it('reports the canonical branch name when a tag has the same name', async () => {
    await git('tag', 'main');

    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.branch).toBe('main');
  });

  it('reports the breadcrumb independently of upstream tracking', async () => {
    await git('config', 'branch.main.emdash-pr-url', 'https://github.com/acme/app/pull/9');

    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.upstream).toBeNull();
    expect(observed?.prBreadcrumb).toBe('https://github.com/acme/app/pull/9');
  });

  it('degrades remoteUrl to null when the remote does not resolve', async () => {
    await git('config', 'branch.main.remote', 'gone');
    await git('config', 'branch.main.merge', 'refs/heads/main');

    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.upstream).toEqual({
      remote: 'gone',
      mergeRef: 'refs/heads/main',
      remoteUrl: null,
    });
  });

  it('matches the branch config literally when the branch name has regex metacharacters', async () => {
    await git('checkout', '-b', 'release/1.2+x');
    await git('config', 'branch.release/1.2+x.emdash-pr-url', 'https://github.com/a/b/pull/3');
    // A decoy the unescaped pattern `1.2+x` would also match.
    await git('config', 'branch.release/1a22x.emdash-pr-url', 'https://github.com/a/b/pull/4');

    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.branch).toBe('release/1.2+x');
    expect(observed?.prBreadcrumb).toBe('https://github.com/a/b/pull/3');
  });

  it('nulls upstream and breadcrumb on detached HEAD but still reports headOid', async () => {
    await git('config', 'branch.main.remote', 'origin');
    await git('config', 'branch.main.merge', 'refs/heads/main');
    await git('config', 'branch.main.emdash-pr-url', 'https://github.com/acme/app/pull/7');
    await git('checkout', '--detach');

    const observed = await observeWorkspaceGit(gitContext, repo);

    expect(observed?.branch).toBeNull();
    expect(observed?.headOid).toBe(await headOidOf(repo));
    expect(observed?.upstream).toBeNull();
    expect(observed?.prBreadcrumb).toBeNull();
  });

  it('serves the remote URL from the per-cycle cache without probing git', async () => {
    // No `origin` remote exists: only the cache can supply this URL.
    await git('config', 'branch.main.remote', 'origin');
    await git('config', 'branch.main.merge', 'refs/heads/main');
    const cache = createRemoteUrlCache();
    cache.set('origin', 'https://cached.example/app.git');

    const observed = await observeWorkspaceGit(gitContext, repo, undefined, {
      remoteUrlCache: cache,
    });

    expect(observed?.upstream?.remoteUrl).toBe('https://cached.example/app.git');
  });
});

describe('observeWorkspaceGitRefs', () => {
  beforeEach(async () => {
    await git('branch', '-M', 'main');
  });

  it('re-reads head OID, upstream, and breadcrumb on a branch switch, carrying dirty state', async () => {
    await git('remote', 'add', 'origin', 'https://example.com/acme/app.git');
    await git('config', 'branch.main.remote', 'origin');
    await git('config', 'branch.main.merge', 'refs/heads/main');
    await git('config', 'branch.main.emdash-pr-url', 'https://github.com/acme/app/pull/7');
    await writeFile(join(repo, 'wip.txt'), 'wip\n');
    const previous = await observeWorkspaceGit(gitContext, repo, undefined, {
      untrackedCache: createUntrackedLinesCache(),
    });
    expect(previous?.upstream).not.toBeNull();
    expect(previous?.dirty).toBe(true);

    // A plain new branch carries no tracking config and no breadcrumb.
    await git('checkout', '-b', 'other');
    const observed = await observeWorkspaceGitRefs(gitContext, repo, previous);

    expect(observed?.branch).toBe('other');
    expect(observed?.headOid).toBe(await headOidOf(repo));
    expect(observed?.upstream).toBeNull();
    expect(observed?.prBreadcrumb).toBeNull();
    // Carried forward from the previous full observation, not re-probed.
    expect(observed?.dirty).toBe(true);
    expect(observed?.diffStats).toEqual(previous?.diffStats);
  });
});
