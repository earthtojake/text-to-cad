import type { GitChange } from '@emdash/core/runtimes/git/api';
import { makeAutoObservable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import { type PrStore } from '@core/features/source-control/api/browser/stores/pr-store';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { type GitCheckoutStore } from '../../stores/git-checkout-store';
import {
  ChangesViewStore,
  type ExpandedSections,
  type ExpandedSectionsPersistence,
} from './changes-view-store';

class FakeGitCheckoutStore {
  unstagedFileChanges: GitChange[] = [];
  stagedFileChanges: GitChange[] = [];
  isLoading = true;
  error: string | undefined = undefined;

  constructor() {
    makeAutoObservable(this);
  }

  setStatus({
    unstaged = this.unstagedFileChanges,
    staged = this.stagedFileChanges,
  }: {
    unstaged?: GitChange[];
    staged?: GitChange[];
  }) {
    this.unstagedFileChanges = unstaged;
    this.stagedFileChanges = staged;
    this.isLoading = false;
  }
}

class FakePrStore {
  pullRequests: unknown[] = [];

  constructor() {
    makeAutoObservable(this);
  }

  setPullRequests(count: number) {
    this.pullRequests = Array.from({ length: count }, (_, i) => ({ id: i }));
  }
}

class FakeSectionsPersistence implements ExpandedSectionsPersistence {
  value: ExpandedSections | undefined;

  constructor(initial?: ExpandedSections) {
    this.value = initial;
    makeAutoObservable(this);
  }

  set(next: ExpandedSections) {
    this.value = next;
  }
}

const change = (path: string): GitChange => ({
  path: portablePath(path),
  status: 'modified',
  additions: 1,
  deletions: 0,
});

function createStore(persisted?: ExpandedSections) {
  const git = new FakeGitCheckoutStore();
  const pr = new FakePrStore();
  const persistence = new FakeSectionsPersistence(persisted);
  const store = new ChangesViewStore(
    git as unknown as GitCheckoutStore,
    pr as unknown as PrStore,
    persistence
  );

  return { git, pr, persistence, store };
}

describe('ChangesViewStore expanded sections', () => {
  it('opens changed files by default after the first git load', () => {
    const { git, store } = createStore();

    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));

    expect(store.expandedSections).toEqual({
      unstaged: true,
      staged: false,
      pullRequests: false,
    });
  });

  it('opens pull requests on the first load when pull requests exist', () => {
    const { git, pr, store } = createStore();

    runInAction(() => {
      pr.setPullRequests(1);
      git.setStatus({ unstaged: [], staged: [] });
    });

    expect(store.expandedSections).toEqual({
      unstaged: false,
      staged: false,
      pullRequests: true,
    });
  });

  it('opens staged files and closes changed files when the last changed file is staged', () => {
    const { git, store } = createStore();

    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));
    runInAction(() => git.setStatus({ unstaged: [], staged: [change('src/a.ts')] }));

    expect(store.expandedSections).toEqual({
      unstaged: false,
      staged: true,
      pullRequests: false,
    });
  });

  it('keeps changed files open when staging leaves other changed files behind', () => {
    const { git, store } = createStore();

    runInAction(() =>
      git.setStatus({ unstaged: [change('src/a.ts'), change('src/b.ts')], staged: [] })
    );
    runInAction(() =>
      git.setStatus({ unstaged: [change('src/b.ts')], staged: [change('src/a.ts')] })
    );

    expect(store.expandedSections).toEqual({
      unstaged: true,
      staged: true,
      pullRequests: false,
    });
  });

  it('removes only completed unstaged paths so newer selections survive', () => {
    const { git, store } = createStore();

    runInAction(() =>
      git.setStatus({
        unstaged: [change('src/a.ts'), change('src/b.ts'), change('src/c.ts')],
        staged: [],
      })
    );

    store.toggleUnstagedItem('src/a.ts');
    store.toggleUnstagedItem('src/b.ts');

    // The user selects another file while staging a.ts is still in flight.
    store.toggleUnstagedItem('src/c.ts');
    store.removeUnstagedSelection(['src/a.ts']);

    expect([...store.unstagedSelection]).toEqual(['src/b.ts', 'src/c.ts']);
  });

  it('removes only completed staged paths so newer selections survive', () => {
    const { git, store } = createStore();

    runInAction(() =>
      git.setStatus({
        unstaged: [],
        staged: [change('src/a.ts'), change('src/b.ts'), change('src/c.ts')],
      })
    );

    store.toggleStagedItem('src/a.ts');
    store.toggleStagedItem('src/b.ts');

    // The user selects another file while unstaging a.ts is still in flight.
    store.toggleStagedItem('src/c.ts');
    store.removeStagedSelection(['src/a.ts']);

    expect([...store.stagedSelection]).toEqual(['src/b.ts', 'src/c.ts']);
  });
});

describe('ChangesViewStore expansion persistence', () => {
  it('defaults to all sections expanded before anything is persisted', () => {
    const { store } = createStore();

    expect(store.expandedSections).toEqual({
      unstaged: true,
      staged: true,
      pullRequests: true,
    });
  });

  it('persists the computed initial expansion after the first git load', () => {
    const { git, persistence, store } = createStore();

    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));

    expect(store.expandedSections).toEqual({
      unstaged: true,
      staged: false,
      pullRequests: false,
    });
    expect(persistence.value).toEqual({
      unstaged: true,
      staged: false,
      pullRequests: false,
    });
  });

  it('keeps a persisted expansion state across the first git load', () => {
    const persisted: ExpandedSections = { unstaged: false, staged: false, pullRequests: false };
    const { git, store } = createStore(persisted);

    // The initial load transition (counts 0 → N) must not auto-expand over
    // the persisted state.
    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));

    expect(store.expandedSections).toEqual(persisted);
  });

  it('writes toggleExpanded through to persistence', () => {
    const { git, persistence, store } = createStore();

    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));
    store.toggleExpanded('staged');

    expect(store.expandedSections.staged).toBe(true);
    expect(persistence.value?.staged).toBe(true);
  });

  it('collapseSection collapses an expanded section and is a no-op when already collapsed', () => {
    const { git, persistence, store } = createStore();

    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));
    store.collapseSection('unstaged');

    expect(store.expandedSections.unstaged).toBe(false);

    const afterFirstCollapse = persistence.value;
    store.collapseSection('unstaged');
    expect(persistence.value).toBe(afterFirstCollapse);
  });

  it('auto-expands a persisted-collapsed section when it gains entries after load', () => {
    const persisted: ExpandedSections = { unstaged: false, staged: false, pullRequests: false };
    const { git, persistence, store } = createStore(persisted);

    runInAction(() => git.setStatus({ unstaged: [], staged: [] }));
    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));

    expect(store.expandedSections.unstaged).toBe(true);
    expect(persistence.value?.unstaged).toBe(true);
  });

  it('suppressNextAutoExpand skips one auto-expand and then resumes', () => {
    const { git, store } = createStore();

    runInAction(() => git.setStatus({ unstaged: [change('src/a.ts')], staged: [] }));

    store.suppressNextAutoExpand('staged');
    runInAction(() => git.setStatus({ unstaged: [], staged: [change('src/a.ts')] }));
    expect(store.expandedSections.staged).toBe(false);

    runInAction(() => git.setStatus({ unstaged: [], staged: [] }));
    runInAction(() => git.setStatus({ unstaged: [], staged: [change('src/a.ts')] }));
    expect(store.expandedSections.staged).toBe(true);
  });
});
