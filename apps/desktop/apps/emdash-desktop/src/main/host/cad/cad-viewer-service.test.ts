import { describe, expect, it } from 'vitest';
import {
  buildCadViewerUrl,
  CadViewerLifecycleRegistry,
  CadViewerProcessLifecycle,
  parseCadViewerLaunch,
  preferredCadViewerPath,
} from './cad-viewer-service';

class FakeViewerChild {
  killCount = 0;
  private readonly terminationListeners: Array<() => void> = [];

  kill(): boolean {
    this.killCount += 1;
    return true;
  }

  onTerminated(listener: () => void): void {
    this.terminationListeners.push(listener);
  }

  terminate(): void {
    for (const listener of this.terminationListeners.splice(0)) listener();
  }
}

describe('buildCadViewerUrl', () => {
  it('encodes the workspace and selects the project-relative CAD file', () => {
    expect(
      buildCadViewerUrl({
        workspacePath: '/Users/amy/My CAD Project',
        relativeFilePath: 'models/front bracket.step',
        port: 3245,
      })
    ).toBe('http://127.0.0.1:3245/?file=models%2Ffront+bracket.step');
  });
});

describe('preferredCadViewerPath', () => {
  const existing = (candidate: string) => candidate.endsWith('bracket.step.py');

  it('keeps the accepted STEP artifact even when legacy source exists beside it', () => {
    expect(preferredCadViewerPath('/project/bracket.step', existing)).toBe('/project/bracket.step');
  });

  it('keeps a STEP artifact when no generator exists', () => {
    expect(preferredCadViewerPath('/project/standalone.step', existing)).toBe(
      '/project/standalone.step'
    );
  });

  it('does not substitute generators for other CAD formats', () => {
    expect(preferredCadViewerPath('/project/bracket.stl', () => true)).toBe('/project/bracket.stl');
  });
});

describe('parseCadViewerLaunch', () => {
  it('reads the launcher contract from the last JSON line', () => {
    expect(
      parseCadViewerLaunch(
        'Starting CAD Viewer at http://127.0.0.1:3246/ (serving /p)\nCAD Viewer URL: http://127.0.0.1:3246/\n{"url":"http://127.0.0.1:3246/","port":3246,"action":"started"}\n'
      )
    ).toEqual({ url: 'http://127.0.0.1:3246/', port: 3246, action: 'started' });
    expect(
      parseCadViewerLaunch('{"url":"http://127.0.0.1:3245/","port":3245,"action":"reused"}')
    ).toEqual({
      url: 'http://127.0.0.1:3245/',
      port: 3245,
      action: 'reused',
    });
  });

  it('ignores partial output and unknown shapes', () => {
    expect(parseCadViewerLaunch('{"url":"http://127.0.0.1:3246/","po')).toBeNull();
    expect(parseCadViewerLaunch('{"ok":true}')).toBeNull();
    expect(parseCadViewerLaunch('')).toBeNull();
  });
});

describe('CadViewerProcessLifecycle', () => {
  it('shares one in-progress startup across concurrent CAD opens', async () => {
    const lifecycle = new CadViewerProcessLifecycle();
    const child = new FakeViewerChild();
    let notifyStarted!: () => void;
    const startupBegan = new Promise<void>((resolve) => {
      notifyStarted = resolve;
    });
    let releaseStartup!: () => void;
    const startupGate = new Promise<void>((resolve) => {
      releaseStartup = resolve;
    });
    let startCount = 0;

    const first = lifecycle.ensureStarted({
      isHealthy: async () => false,
      start: async () => {
        startCount += 1;
        lifecycle.adopt(child);
        notifyStarted();
        await startupGate;
        expect(lifecycle.markReady(child, 3247)).toBe(true);
        return { success: true, port: 3247 };
      },
    });
    await startupBegan;
    const second = lifecycle.ensureStarted({
      isHealthy: async () => false,
      start: async () => {
        throw new Error('concurrent caller must not start a second viewer');
      },
    });

    expect(second).toBe(first);
    releaseStartup();
    await expect(Promise.all([first, second])).resolves.toEqual([
      { success: true, port: 3247 },
      { success: true, port: 3247 },
    ]);
    expect(startCount).toBe(1);
    expect(child.killCount).toBe(0);
  });

  it('does not let a replaced child clear ownership when its exit arrives late', async () => {
    const lifecycle = new CadViewerProcessLifecycle();
    const oldChild = new FakeViewerChild();
    const newChild = new FakeViewerChild();

    await lifecycle.ensureStarted({
      isHealthy: async () => false,
      start: async () => {
        lifecycle.adopt(oldChild);
        expect(lifecycle.markReady(oldChild, 3245)).toBe(true);
        return { success: true, port: 3245 };
      },
    });
    await lifecycle.ensureStarted({
      isHealthy: async () => false,
      start: async () => {
        lifecycle.adopt(newChild);
        expect(lifecycle.markReady(newChild, 3247)).toBe(true);
        return { success: true, port: 3247 };
      },
    });

    expect(oldChild.killCount).toBe(1);
    oldChild.terminate();
    let unexpectedStarts = 0;
    await expect(
      lifecycle.ensureStarted({
        isHealthy: async (port) => port === 3247,
        start: async () => {
          unexpectedStarts += 1;
          return { success: false, error: 'unexpected restart' };
        },
      })
    ).resolves.toEqual({ success: true, port: 3247 });
    expect(unexpectedStarts).toBe(0);
    expect(newChild.killCount).toBe(0);
  });

  it('terminates an adopted child when startup fails or times out', async () => {
    const lifecycle = new CadViewerProcessLifecycle();
    const timedOutChild = new FakeViewerChild();

    await expect(
      lifecycle.ensureStarted({
        isHealthy: async () => false,
        start: async () => {
          lifecycle.adopt(timedOutChild);
          return { success: false, error: 'CAD Viewer startup timed out' };
        },
      })
    ).resolves.toEqual({ success: false, error: 'CAD Viewer startup timed out' });
    expect(timedOutChild.killCount).toBe(1);
  });
});

describe('CadViewerProcessLifecycle reuse', () => {
  it('keeps a reused external viewer without owning a process, and never kills it', async () => {
    const lifecycle = new CadViewerProcessLifecycle();
    const launcher = new FakeViewerChild();
    await lifecycle.ensureStarted({
      isHealthy: async () => false,
      start: async () => {
        lifecycle.adopt(launcher);
        lifecycle.markExternal(3245);
        launcher.terminate();
        return { success: true, port: 3245 };
      },
    });
    expect(lifecycle.port).toBe(3245);
    expect(launcher.killCount).toBe(0);

    let starts = 0;
    await expect(
      lifecycle.ensureStarted({
        isHealthy: async (port) => port === 3245,
        start: async () => {
          starts += 1;
          return { success: false, error: 'must reuse the healthy viewer' };
        },
      })
    ).resolves.toEqual({ success: true, port: 3245 });
    expect(starts).toBe(0);

    lifecycle.stop();
    expect(lifecycle.port).toBeNull();
    expect(launcher.killCount).toBe(0);
  });
});

describe('CadViewerLifecycleRegistry', () => {
  it('keeps different workspace roots alive in independent lifecycles', async () => {
    const registry = new CadViewerLifecycleRegistry();
    const rootA = registry.forWorkspace('/projects/a');
    const rootB = registry.forWorkspace('/projects/b');
    const childA = new FakeViewerChild();
    const childB = new FakeViewerChild();

    await Promise.all([
      rootA.ensureStarted({
        isHealthy: async () => false,
        start: async () => {
          rootA.adopt(childA);
          expect(rootA.markReady(childA, 3245)).toBe(true);
          return { success: true, port: 3245 };
        },
      }),
      rootB.ensureStarted({
        isHealthy: async () => false,
        start: async () => {
          rootB.adopt(childB);
          expect(rootB.markReady(childB, 3246)).toBe(true);
          return { success: true, port: 3246 };
        },
      }),
    ]);

    expect(rootA).not.toBe(rootB);
    expect(registry.size).toBe(2);
    expect(childA.killCount).toBe(0);
    expect(childB.killCount).toBe(0);

    await expect(
      rootA.ensureStarted({
        isHealthy: async (port) => port === 3245,
        start: async () => ({ success: false, error: 'must not restart root A' }),
      })
    ).resolves.toEqual({ success: true, port: 3245 });
    expect(childB.killCount).toBe(0);
  });

  it('normalizes workspace aliases and stops every owned child', async () => {
    const registry = new CadViewerLifecycleRegistry();
    const rootA = registry.forWorkspace('/projects/a/../a');
    expect(registry.forWorkspace('/projects/a')).toBe(rootA);
    const rootB = registry.forWorkspace('/projects/b');
    const childA = new FakeViewerChild();
    const childB = new FakeViewerChild();
    rootA.adopt(childA);
    rootB.adopt(childB);

    registry.stopAll();

    expect(childA.killCount).toBe(1);
    expect(childB.killCount).toBe(1);
    expect(registry.size).toBe(0);
  });
});
