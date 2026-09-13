import { createScope, type Scope } from '@emdash/shared/concurrency';
import { query, type Query } from '@emdash/wire/state';
import type { PortableRelativePath } from '#primitives/path/api';
import type { BoundGitFileContentKey, GitFileContentState, GitFileSource } from '#runtimes/git/api';
import type { GitCheckout } from './git-checkout';

type ContentInvalidation = 'index' | 'refs' | 'history';

export type GitFileContentRegistryOptions = Readonly<{
  commands: GitCheckout;
  execute: <T>(run: () => Promise<T>) => Promise<T>;
  maxEntries?: number;
  onError?: (context: string, error: unknown) => void;
}>;

type Entry = {
  readonly key: BoundGitFileContentKey;
  readonly scope: Scope;
  readonly state: Query<GitFileContentState>;
  leases: number;
  lastUsed: number;
};

const DEFAULT_MAX_ENTRIES = 256;
const CONTENT_REVALIDATE_MS = 5 * 60_000;
const CONTENT_DEBOUNCE_MS = 25;

/** Bounded, demand-driven live state for Git-owned file revisions. */
export class GitFileContentRegistry {
  private readonly entries = new Map<string, Entry>();
  private readonly maxEntries: number;
  private disposed = false;

  constructor(private readonly options: GitFileContentRegistryOptions) {
    this.maxEntries = Math.max(1, options.maxEntries ?? DEFAULT_MAX_ENTRIES);
  }

  state(key: BoundGitFileContentKey, scope: Scope): Query<GitFileContentState> {
    this.assertActive();
    const id = JSON.stringify([key.path, key.source]);
    let entry = this.entries.get(id);
    if (!entry) {
      entry = this.createEntry(key);
      this.entries.set(id, entry);
    }
    entry.leases += 1;
    entry.lastUsed = Date.now();
    this.evictIdleEntries();

    scope.add(() => this.release(entry));
    return entry.state;
  }

  invalidate(paths: 'all' | readonly PortableRelativePath[], reason: ContentInvalidation): void {
    if (this.disposed) return;
    const selected = paths === 'all' ? undefined : new Set(paths);
    for (const entry of this.entries.values()) {
      if (selected && !selected.has(entry.key.path)) continue;
      if (!affectedBy(entry.key.source, reason)) continue;
      entry.state.invalidate();
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const entry of this.entries.values()) void entry.scope.dispose();
    this.entries.clear();
  }

  private createEntry(key: BoundGitFileContentKey): Entry {
    const scope = createScope({ label: 'git-file-content-state' });
    return {
      key,
      scope,
      state: query({
        fetch: async () => this.options.execute(() => this.options.commands.getFileContent(key)),
        debounceMs: CONTENT_DEBOUNCE_MS,
        revalidateEveryMs: isImmutableSource(key.source) ? undefined : CONTENT_REVALIDATE_MS,
        scope,
        onError: (error) =>
          this.options.onError?.(`git content ${key.path} ${key.source.kind}`, error),
      }),
      leases: 0,
      lastUsed: Date.now(),
    };
  }

  private evictIdleEntries(): void {
    if (this.entries.size <= this.maxEntries) return;
    const idle = [...this.entries.entries()]
      .filter(([, entry]) => entry.leases === 0)
      .sort((left, right) => left[1].lastUsed - right[1].lastUsed);
    for (const [id, entry] of idle) {
      if (this.entries.size <= this.maxEntries) break;
      this.entries.delete(id);
      void entry.scope.dispose();
    }
  }

  private release(entry: Entry): void {
    entry.leases = Math.max(0, entry.leases - 1);
    entry.lastUsed = Date.now();
    this.evictIdleEntries();
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('GitFileContentRegistry is disposed');
  }
}

function affectedBy(source: GitFileSource, reason: ContentInvalidation): boolean {
  if (reason === 'history') return !isImmutableSource(source);
  if (reason === 'index') return source.kind === 'index';
  if (source.kind === 'head') return true;
  return source.kind === 'revision' && !isImmutableSource(source);
}

function isImmutableSource(source: GitFileSource): boolean {
  return (
    source.kind === 'revision' &&
    source.revision.kind === 'commit' &&
    /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/u.test(source.revision.sha)
  );
}
