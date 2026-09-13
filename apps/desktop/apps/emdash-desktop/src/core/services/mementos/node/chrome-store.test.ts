import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { reaction } from 'mobx';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { defineChromeStore } from '@core/primitives/chrome-stores/api';
import { createChromeStore } from '@core/primitives/chrome-stores/browser';
import { defineMemento, mementosWireContract } from '@core/primitives/mementos/api';
import { MementoClient } from '@core/primitives/mementos/browser/memento-client';
import { defineSubject } from '@core/primitives/subjects/api';
import { MementoService } from '@core/services/mementos/node/memento-service';
import {
  MementoPersistenceService,
  mementosSqliteStore,
} from '@core/services/mementos/node/persistence';
import { createMementosWireController } from '@core/services/mementos/node/wire-controller';

const taskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string() }),
  encode: ({ taskId }) => taskId,
});

const chromeSchema = defineVersionedSchema()
  .initial(
    '1',
    z.object({
      version: z.literal('1'),
      sidebarCollapsed: z.boolean(),
      sidebarTab: z.enum(['changes', 'files']),
    })
  )
  .build();

const chromeMemento = defineMemento({
  id: 'test.chrome',
  subject: taskSubject,
  schema: chromeSchema,
  default: {
    version: '1' as const,
    sidebarCollapsed: true,
    sidebarTab: 'changes' as const,
  },
});

/**
 * The documented two-command store with one invariant (see the module
 * docstring of `api/define-chrome-store.ts`): `openSidebarTab` enforces
 * "opening a sidebar tab ⇒ sidebar expanded" inside the command, so no call
 * site can select a tab while leaving the sidebar collapsed.
 */
const chromeStore = defineChromeStore({
  memento: chromeMemento,
  ephemeral: { focusedRegion: undefined as 'sidebar' | undefined },
  commands: {
    toggleSidebar: ({ state }) => ({
      state: { ...state, sidebarCollapsed: !state.sidebarCollapsed },
    }),
    openSidebarTab: ({ state }, tab: 'changes' | 'files') => ({
      state: { ...state, sidebarTab: tab, sidebarCollapsed: false },
      ephemeral: { focusedRegion: 'sidebar' as const },
    }),
    blurSidebar: () => ({ ephemeral: { focusedRegion: undefined } }),
    noop: () => undefined,
  },
});

describe('createChromeStore', () => {
  const cleanups: Array<() => Promise<void>> = [];

  afterEach(async () => {
    vi.useRealTimers();
    await Promise.all(cleanups.splice(0).map(async (cleanup) => await cleanup()));
  });

  it('applies a named command to the state synchronously', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;

    expect(store.state.sidebarCollapsed).toBe(true);
    store.commands.toggleSidebar();
    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('enforces the tab⇒expanded invariant inside one command', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;
    expect(store.state.sidebarCollapsed).toBe(true);

    store.commands.openSidebarTab('files');

    expect(store.state.sidebarTab).toBe('files');
    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('notifies MobX observers once per dispatched command', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;
    const observed: string[] = [];
    const dispose = reaction(
      () => store.state,
      (state) => observed.push(state.sidebarTab)
    );

    store.commands.openSidebarTab('files');

    expect(observed).toEqual(['files']);
    dispose();
  });

  it('writes command results through the memento document', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;

    store.commands.openSidebarTab('files');
    await store.flush();

    expect(setup.persistence.snapshot()).toHaveLength(1);

    const secondClient = new MementoClient(setup.wire.client, { registerBeforeUnload: false });
    cleanups.push(() => secondClient.dispose());
    const secondSpace = secondClient.subject(taskSubject({ taskId: 'task-1' }));
    const secondStore = createChromeStore(chromeStore, secondSpace);
    await secondSpace.ready;

    expect(secondStore.state).toEqual({
      version: '1',
      sidebarCollapsed: false,
      sidebarTab: 'files',
    });
  });

  it('skips the persistence write when a command returns unchanged state', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;

    store.commands.openSidebarTab('files');
    await store.flush();
    expect(setup.persistence.snapshot()).toHaveLength(1);
    setup.persistence.deleteAll();

    // Structurally identical result: the sidebar is already expanded on 'files'.
    store.commands.openSidebarTab('files');
    await store.flush();

    expect(setup.persistence.snapshot()).toEqual([]);
  });

  it('leaves state and persistence untouched when a command returns nothing', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;
    const before = store.state;

    store.commands.noop();
    await store.flush();

    expect(store.state).toBe(before);
    expect(setup.persistence.snapshot()).toEqual([]);
  });

  it('sets ephemeral fields only through commands and never persists them', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);
    await space.ready;
    const observed: Array<'sidebar' | undefined> = [];
    const dispose = reaction(
      () => store.ephemeral.focusedRegion,
      (region) => observed.push(region)
    );

    expect(store.ephemeral.focusedRegion).toBeUndefined();
    store.commands.openSidebarTab('files');
    expect(store.ephemeral.focusedRegion).toBe('sidebar');
    store.commands.blurSidebar();
    expect(store.ephemeral.focusedRegion).toBeUndefined();
    expect(observed).toEqual(['sidebar', undefined]);
    dispose();

    store.commands.openSidebarTab('changes');
    await store.flush();

    const [row] = setup.persistence.snapshot();
    expect(JSON.parse(row!.data)).not.toHaveProperty('focusedRegion');
  });

  it('does not share ephemeral state across instances', async () => {
    const setup = await createSetup(cleanups);
    const firstSpace = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const secondSpace = setup.client.subject(taskSubject({ taskId: 'task-2' }));
    const first = createChromeStore(chromeStore, firstSpace);
    const second = createChromeStore(chromeStore, secondSpace);
    await Promise.all([firstSpace.ready, secondSpace.ready]);

    first.commands.openSidebarTab('files');

    expect(first.ephemeral.focusedRegion).toBe('sidebar');
    expect(second.ephemeral.focusedRegion).toBeUndefined();
  });

  it('dev-asserts state reads and dispatch before the subject space hydrates', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const store = createChromeStore(chromeStore, space);

    if (import.meta.env.DEV) {
      expect(() => store.state).toThrowError(/before its subject space hydrated/);
      expect(() => store.commands.toggleSidebar()).toThrowError(
        /before its subject space hydrated/
      );
    }

    await space.ready;

    expect(store.state.sidebarCollapsed).toBe(true);
    store.commands.toggleSidebar();
    expect(store.state.sidebarCollapsed).toBe(false);
  });
});

async function createSetup(cleanups: Array<() => Promise<void>>): Promise<{
  client: MementoClient;
  persistence: MementoPersistenceService;
  service: MementoService;
  wire: TestWire<typeof mementosWireContract>;
}> {
  const handle = await mementosSqliteStore.openTemp();
  const persistence = new MementoPersistenceService(handle);
  const service = new MementoService({ persistence });
  const wire = createTestWire(mementosWireContract, createMementosWireController(service));
  const client = new MementoClient(wire.client, { registerBeforeUnload: false });
  cleanups.push(async () => {
    await client.dispose();
    await wire.dispose();
    await service.dispose();
  });
  return { client, persistence, service, wire };
}
