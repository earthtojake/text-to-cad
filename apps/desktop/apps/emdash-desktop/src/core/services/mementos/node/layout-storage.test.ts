import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { createTestWire } from '@emdash/wire/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { defineMemento, mementosWireContract } from '@core/primitives/mementos/api';
import { createLayoutStorage } from '@core/primitives/mementos/browser/layout-storage';
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

// Mirrors the real panel-layouts memento shape (`tasks.panel-layouts` /
// `projects.panel-layouts`); the catalog test in
// src/core/manifests/shared/memento-catalog.test.ts covers the real
// definitions, which module boundaries keep out of services tests.
const panelLayoutsSchema = defineVersionedSchema()
  .initial(
    '1',
    z.object({
      version: z.literal('1'),
      layouts: z.record(z.string(), z.string()),
    })
  )
  .build();
const panelLayoutsMemento = defineMemento({
  id: 'tasks.panel-layouts',
  subject: taskSubject,
  schema: panelLayoutsSchema,
  default: { version: '1' as const, layouts: {} },
});

const SIDEBAR_KEY = 'react-resizable-panels:task-sidebar-split';
const SECTIONS_KEY = 'react-resizable-panels:changes-sections:staged,unstaged';
const SIDEBAR_LAYOUT = '{"sidebar":30,"main":70}';
const SECTIONS_LAYOUT = '{"staged":40,"unstaged":60}';

describe('createLayoutStorage', () => {
  const cleanups: Array<() => Promise<void>> = [];

  afterEach(async () => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    await Promise.all(cleanups.splice(0).map(async (cleanup) => await cleanup()));
  });

  it('round-trips layouts through the memento and reads missing keys as null', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);
    await space.ready;

    expect(storage.getItem(SIDEBAR_KEY)).toBeNull();

    storage.setItem(SIDEBAR_KEY, SIDEBAR_LAYOUT);
    expect(storage.getItem(SIDEBAR_KEY)).toBe(SIDEBAR_LAYOUT);
    expect(storage.getItem(SECTIONS_KEY)).toBeNull();
    await setup.client.flush();

    const secondClient = new MementoClient(setup.wire.client, { registerBeforeUnload: false });
    cleanups.push(() => secondClient.dispose());
    const secondSpace = secondClient.subject(taskSubject({ taskId: 'task-1' }));
    const secondStorage = createLayoutStorage(secondSpace, panelLayoutsMemento);
    await secondSpace.ready;

    expect(secondStorage.getItem(SIDEBAR_KEY)).toBe(SIDEBAR_LAYOUT);
  });

  it('returns value-stable strings for unchanged layouts across the authoritative echo', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);
    await space.ready;

    storage.setItem(SIDEBAR_KEY, SIDEBAR_LAYOUT);
    const beforeEcho = storage.getItem(SIDEBAR_KEY);
    expect(storage.getItem(SIDEBAR_KEY)).toBe(beforeEcho);

    await setup.client.flush();

    expect(storage.getItem(SIDEBAR_KEY)).toBe(beforeEcho);
    expect(storage.getItem(SIDEBAR_KEY)).toBe(storage.getItem(SIDEBAR_KEY));
  });

  it('writes through the debounced memento path', async () => {
    vi.useFakeTimers();
    const setup = await createSetup(cleanups, { debounceMs: 50 });
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);
    await readyWithFakeTimers(space.ready);

    storage.setItem(SIDEBAR_KEY, SIDEBAR_LAYOUT);
    expect(setup.persistence.snapshot()).toEqual([]);

    await vi.advanceTimersByTimeAsync(50);

    const rows = setup.persistence.snapshot();
    expect(rows).toHaveLength(1);
    expect(JSON.parse(rows[0]!.data)).toEqual({
      version: '1',
      layouts: { [SIDEBAR_KEY]: SIDEBAR_LAYOUT },
    });
  });

  it('coalesces consecutive writes into one debounced save', async () => {
    vi.useFakeTimers();
    const setup = await createSetup(cleanups, { debounceMs: 50 });
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);
    await readyWithFakeTimers(space.ready);

    storage.setItem(SIDEBAR_KEY, SIDEBAR_LAYOUT);
    await vi.advanceTimersByTimeAsync(30);
    storage.setItem(SECTIONS_KEY, SECTIONS_LAYOUT);
    await vi.advanceTimersByTimeAsync(30);
    expect(setup.persistence.snapshot()).toEqual([]);

    await vi.advanceTimersByTimeAsync(20);

    const rows = setup.persistence.snapshot();
    expect(rows).toHaveLength(1);
    expect(JSON.parse(rows[0]!.data)).toEqual({
      version: '1',
      layouts: {
        [SIDEBAR_KEY]: SIDEBAR_LAYOUT,
        [SECTIONS_KEY]: SECTIONS_LAYOUT,
      },
    });
  });

  it('fails a dev assertion for any access before the space hydrates', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);

    expect(space.isHydrated).toBe(false);
    expect(() => storage.getItem(SIDEBAR_KEY)).toThrowError(/isHydrated/);
    expect(() => storage.setItem(SIDEBAR_KEY, SIDEBAR_LAYOUT)).toThrowError(/isHydrated/);

    await space.ready;
    expect(() => storage.getItem(SIDEBAR_KEY)).not.toThrow();
  });

  it('logs and returns the in-memory value for pre-hydration reads in production', async () => {
    vi.stubEnv('DEV', false);
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);

    expect(space.isHydrated).toBe(false);
    expect(storage.getItem(SIDEBAR_KEY)).toBeNull();
    expect(error).toHaveBeenCalledOnce();

    await space.ready;
  });

  it('deletes one entry and persists the removal without touching siblings', async () => {
    const setup = await createSetup(cleanups);
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);
    await space.ready;
    storage.setItem(SIDEBAR_KEY, SIDEBAR_LAYOUT);
    storage.setItem(SECTIONS_KEY, SECTIONS_LAYOUT);
    await setup.client.flush();

    storage.deleteEntry(SIDEBAR_KEY);

    expect(storage.getItem(SIDEBAR_KEY)).toBeNull();
    expect(storage.getItem(SECTIONS_KEY)).toBe(SECTIONS_LAYOUT);
    await setup.client.flush();

    const rows = setup.persistence.snapshot();
    expect(rows).toHaveLength(1);
    expect(JSON.parse(rows[0]!.data)).toEqual({
      version: '1',
      layouts: { [SECTIONS_KEY]: SECTIONS_LAYOUT },
    });
  });

  it('does not schedule a write when deleting an absent entry', async () => {
    vi.useFakeTimers();
    const setup = await createSetup(cleanups, { debounceMs: 50 });
    const space = setup.client.subject(taskSubject({ taskId: 'task-1' }));
    const storage = createLayoutStorage(space, panelLayoutsMemento);
    await readyWithFakeTimers(space.ready);

    storage.deleteEntry(SIDEBAR_KEY);
    await vi.advanceTimersByTimeAsync(50);

    expect(setup.persistence.snapshot()).toEqual([]);
  });
});

/**
 * Awaits readiness under fake timers: the service-side query schedules its
 * initial fetch on a zero-delay timer, so fake timers must be pumped for the
 * ready promise to resolve.
 */
async function readyWithFakeTimers(ready: Promise<void>): Promise<void> {
  let settled = false;
  const tracked = ready.then(() => {
    settled = true;
  });
  for (let attempt = 0; attempt < 20 && !settled; attempt += 1) {
    await vi.advanceTimersByTimeAsync(0);
  }
  await tracked;
}

async function createSetup(
  cleanups: Array<() => Promise<void>>,
  options: { debounceMs?: number } = {}
) {
  const handle = await mementosSqliteStore.openTemp();
  const persistence = new MementoPersistenceService(handle);
  const service = new MementoService({ persistence });
  const wire = createTestWire(mementosWireContract, createMementosWireController(service));
  const client = new MementoClient(wire.client, {
    debounceMs: options.debounceMs,
    registerBeforeUnload: false,
  });
  cleanups.push(async () => {
    await client.dispose();
    await wire.dispose();
    await service.dispose();
  });
  return { client, persistence, service, wire };
}
