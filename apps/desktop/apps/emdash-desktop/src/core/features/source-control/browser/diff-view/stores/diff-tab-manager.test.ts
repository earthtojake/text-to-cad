import { observable, runInAction } from 'mobx';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { DiffTabManager } from './diff-tab-manager';

// ---------------------------------------------------------------------------
// Minimal fakes — no full store stack required.
// ---------------------------------------------------------------------------

function makeFakeResource(
  opts: Partial<{
    path: string;
    diffGroup: 'disk' | 'staged' | 'git' | 'pr';
    prNumber: number;
    tabId: string;
  }> = {}
) {
  const resource = {
    path: portablePath(opts.path ?? 'src/foo.ts'),
    diffGroup: opts.diffGroup ?? 'disk',
    prNumber: opts.prNumber,
    tabId: opts.tabId ?? 'tab-1',
    closeSelf: vi.fn(),
    transition: vi.fn(),
    onActivate: vi.fn(),
    toActiveFile: vi.fn(() => ({
      path: resource.path,
      type: 'disk' as const,
      group: resource.diffGroup,
      originalRef: { kind: 'commit', sha: 'HEAD' } as const,
    })),
  };
  return resource;
}

function makeFakeSession(
  unstagedPaths: string[] = [],
  stagedPaths: string[] = [],
  diffViewSetActiveFile = vi.fn()
) {
  const session = {
    gitCheckout: {
      unstagedFileChanges: observable.array(unstagedPaths.map((p) => ({ path: p, status: 'M' }))),
      stagedFileChanges: observable.array(stagedPaths.map((p) => ({ path: p, status: 'M' }))),
    },
    pr: { pullRequests: [], getFiles: vi.fn(() => ({ data: [] })) },
    diffView: { setActiveFile: diffViewSetActiveFile },
  };
  return session;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DiffTabManager: acquire / release', () => {
  it('tracks resources in the acquired set', () => {
    const manager = new DiffTabManager();
    const r = makeFakeResource();
    manager.acquire(r as never);
    expect(manager['_resources'].has(r as never)).toBe(true);
    manager.release(r as never);
    expect(manager['_resources'].has(r as never)).toBe(false);
  });

  it('dispose clears all resources', () => {
    const manager = new DiffTabManager();
    manager.acquire(makeFakeResource({ tabId: 'a' }) as never);
    manager.acquire(makeFakeResource({ tabId: 'b' }) as never);
    manager.dispose();
    expect(manager['_resources'].size).toBe(0);
  });
});

describe('DiffTabManager: currentDiffView', () => {
  it('returns null before bindSession', () => {
    const manager = new DiffTabManager();
    expect(manager.currentDiffView()).toBeNull();
    manager.dispose();
  });

  it('returns the diffView after bindSession and null after unbindSession', () => {
    const manager = new DiffTabManager();
    const session = makeFakeSession();
    manager.bindSession(session as never);
    expect(manager.currentDiffView()).toBe(session.diffView);
    manager.unbindSession();
    expect(manager.currentDiffView()).toBeNull();
    manager.dispose();
  });
});

describe('DiffTabManager: staleness reconcile', () => {
  let manager: DiffTabManager;

  beforeEach(() => {
    manager = new DiffTabManager();
  });

  it('auto-closes a stale disk resource when its file disappears from both git lists', () => {
    const resource = makeFakeResource({ path: 'src/gone.ts', diffGroup: 'disk' });
    manager.acquire(resource as never);

    // Start with the file present so the reaction is tracking it.
    const session = makeFakeSession(['src/gone.ts'], []);
    manager.bindSession(session as never);

    // Remove the file — reaction fires and sees the resource is now stale.
    runInAction(() => {
      (session.gitCheckout.unstagedFileChanges as ReturnType<typeof observable.array>).replace([]);
    });

    expect(resource.closeSelf).toHaveBeenCalled();
    manager.dispose();
  });

  it('keeps an open disk resource when another changed file appears', () => {
    const resource = makeFakeResource({ path: 'src/open.ts', diffGroup: 'disk' });
    manager.acquire(resource as never);

    const session = makeFakeSession(['src/open.ts'], []);
    manager.bindSession(session as never);

    runInAction(() => {
      (session.gitCheckout.unstagedFileChanges as ReturnType<typeof observable.array>).replace([
        { path: 'src/open.ts', status: 'M' },
        { path: 'src/new.ts', status: 'M' },
      ]);
    });

    expect(resource.closeSelf).not.toHaveBeenCalled();
    manager.dispose();
  });

  it('transitions a disk resource to staged when its file moves to the index', () => {
    const resource = makeFakeResource({ path: 'src/moved.ts', diffGroup: 'disk' });
    manager.acquire(resource as never);

    // Start with file unstaged.
    const session = makeFakeSession(['src/moved.ts'], []);
    manager.bindSession(session as never);

    // Move to staged.
    runInAction(() => {
      (session.gitCheckout.unstagedFileChanges as ReturnType<typeof observable.array>).replace([]);
      (session.gitCheckout.stagedFileChanges as ReturnType<typeof observable.array>).replace([
        { path: 'src/moved.ts', status: 'M' },
      ]);
    });

    expect(resource.transition).toHaveBeenCalledWith('staged', expect.anything(), 'M');
    expect(resource.closeSelf).not.toHaveBeenCalled();
    manager.dispose();
  });

  it('does not close git-group resources regardless of git lists', () => {
    const resource = makeFakeResource({ path: 'src/git.ts', diffGroup: 'git' });
    manager.acquire(resource as never);

    // Empty git lists — git-group should be immune.
    const session = makeFakeSession([], []);
    manager.bindSession(session as never);

    runInAction(() => {
      (session.gitCheckout.unstagedFileChanges as ReturnType<typeof observable.array>).replace([]);
    });

    expect(resource.closeSelf).not.toHaveBeenCalled();
    manager.dispose();
  });

  it('stops the staleness reaction after unbindSession', () => {
    const resource = makeFakeResource({ path: 'src/a.ts', diffGroup: 'disk' });
    manager.acquire(resource as never);

    const session = makeFakeSession(['src/a.ts'], []);
    manager.bindSession(session as never);
    manager.unbindSession();

    // Removing the file after unbind should NOT trigger close.
    runInAction(() => {
      (session.gitCheckout.unstagedFileChanges as ReturnType<typeof observable.array>).replace([]);
    });

    expect(resource.closeSelf).not.toHaveBeenCalled();
    manager.dispose();
  });
});

describe('DiffTabManager: onActivate -> setActiveFile', () => {
  it('resource.onActivate() pushes activeFile to the bound diffView', () => {
    const setActiveFile = vi.fn();
    const manager = new DiffTabManager();
    const resource = makeFakeResource();

    // Simulate what DiffTabResource does: store the manager and call in onActivate.
    const fakeOnActivate = () => {
      manager.currentDiffView()?.setActiveFile(resource.toActiveFile());
    };

    manager.acquire(resource as never);
    const session = makeFakeSession([], [], setActiveFile);
    manager.bindSession(session as never);

    fakeOnActivate();

    expect(setActiveFile).toHaveBeenCalledWith(resource.toActiveFile());
    manager.dispose();
  });

  it('resource.onActivate() is a no-op when no session is bound', () => {
    const setActiveFile = vi.fn();
    const manager = new DiffTabManager();
    const resource = makeFakeResource();

    const fakeOnActivate = () => {
      manager.currentDiffView()?.setActiveFile(resource.toActiveFile());
    };

    manager.acquire(resource as never);
    fakeOnActivate(); // no session bound yet

    expect(setActiveFile).not.toHaveBeenCalled();
    manager.dispose();
  });
});
