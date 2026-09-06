import { afterEach, describe, expect, it } from 'vitest';
import { createAppScope, getAppStores, resetAppScope } from './app-scope';
import { contributeScopedStore, scopedStoreToken } from './scoped-store-host';

class FakeMachines {
  activated = false;
  disposed = false;
}

const machinesToken = scopedStoreToken<FakeMachines>('test.machines');

function testContributions() {
  return [
    contributeScopedStore({
      token: machinesToken,
      create: () => new FakeMachines(),
      activate: (store) => {
        store.activated = true;
      },
      dispose: (store) => {
        store.disposed = true;
      },
    }),
  ];
}

afterEach(() => {
  resetAppScope();
});

describe('app scope', () => {
  it('throws with a bootstrap-ordering message before createAppScope runs', () => {
    expect(() => getAppStores()).toThrowError(/createAppScope must run in renderer bootstrap/);
  });

  it('creates stores and activates them synchronously', () => {
    createAppScope(testContributions());
    const machines = getAppStores().get(machinesToken);
    expect(machines.activated).toBe(true);
  });

  it('throws when created twice', () => {
    createAppScope(testContributions());
    expect(() => createAppScope(testContributions())).toThrowError(
      /createAppScope was called twice/
    );
  });

  it('resetAppScope disposes stores and allows re-creation', () => {
    createAppScope(testContributions());
    const machines = getAppStores().get(machinesToken);
    resetAppScope();
    expect(machines.disposed).toBe(true);
    expect(() => getAppStores()).toThrowError(/createAppScope must run in renderer bootstrap/);
    createAppScope(testContributions());
    expect(getAppStores().get(machinesToken)).not.toBe(machines);
  });
});
