import { createScope } from '@emdash/shared/concurrency';
import { waitFor } from '@emdash/shared/testing';
import type { LiveSource } from '@emdash/wire/rpc';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { defineSubject } from '@core/primitives/subjects/api';
import { MementoService } from './memento-service';
import { MementoPersistenceService, mementosSqliteStore } from './persistence';

const taskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string() }),
  encode: ({ taskId }) => taskId,
});

describe('MementoService', () => {
  let service: MementoService | undefined;

  afterEach(async () => {
    await service?.dispose();
    service = undefined;
  });

  it('updates only the live model instance addressed by a save', async () => {
    service = await createService();
    const firstKey = { mementoId: 'tasks.drawer', kind: 'task', key: 'task-1' };
    const secondKey = { mementoId: 'tasks.editor', kind: 'task', key: 'task-1' };
    const firstLease = service.host.acquireState(firstKey, 'value');
    const secondLease = service.host.acquireState(secondKey, 'value');
    const first = await firstLease.ready();
    const second = await secondLease.ready();
    const onFirst = vi.fn();
    const onSecond = vi.fn();
    const unsubscribeFirst = await first.subscribe(onFirst);
    const unsubscribeSecond = await second.subscribe(onSecond);

    const row = { version: '1', data: '{"version":"1","open":true}', updatedAt: 10 };
    const result = await service.host.runMutation('save', {
      key: firstKey,
      input: row,
      mutationId: 'save-1',
    });

    expect(result.success).toBe(true);
    expect((await first.snapshot()).data).toEqual({ ...row, updatedAt: 1_000 });
    expect((await second.snapshot()).data).toBeNull();
    expect(onFirst).toHaveBeenCalledTimes(1);
    expect(onSecond).not.toHaveBeenCalled();

    unsubscribeFirst();
    unsubscribeSecond();
    await firstLease.release();
    await secondLease.release();
  });

  it('deletes and invalidates every live memento for one subject', async () => {
    service = await createService();
    const matchingKeys = [
      { mementoId: 'tasks.drawer', kind: 'task', key: 'task-1' },
      { mementoId: 'tasks.editor', kind: 'task', key: 'task-1' },
    ];
    const otherKey = { mementoId: 'tasks.drawer', kind: 'task', key: 'task-2' };
    const leases = [...matchingKeys, otherKey].map((key) =>
      service!.host.acquireState(key, 'value')
    );
    const states = await Promise.all(leases.map((lease) => lease.ready()));

    for (let index = 0; index < leases.length; index++) {
      await service.host.runMutation('save', {
        key: [...matchingKeys, otherKey][index]!,
        input: { version: '1', data: '{}', updatedAt: index + 1 },
        mutationId: `save-${index}`,
      });
    }

    expect(service.deleteBySubject(taskSubject({ taskId: 'task-1' }))).toEqual({
      success: true,
      data: { deleted: 2 },
    });
    // Deletes invalidate live mementos through pokes, so convergence is async.
    await waitFor(async () =>
      (await snapshotData(states.slice(0, 2))).every((data) => data === null)
    );
    expect(await snapshotData(states)).toEqual([
      null,
      null,
      { version: '1', data: '{}', updatedAt: 1_000 },
    ]);

    await Promise.all(leases.map((lease) => lease.release()));
  });

  it('deletes all rows and invalidates every live memento', async () => {
    service = await createService();
    const keys = [
      { mementoId: 'tasks.drawer', kind: 'task', key: 'task-1' },
      { mementoId: 'projects.sidebar', kind: 'project', key: 'project-1' },
    ];
    const leases = keys.map((key) => service!.host.acquireState(key, 'value'));
    const states = await Promise.all(leases.map((lease) => lease.ready()));
    for (let index = 0; index < keys.length; index++) {
      await service.host.runMutation('save', {
        key: keys[index]!,
        input: { version: '1', data: '{}', updatedAt: index },
        mutationId: `save-all-${index}`,
      });
    }

    expect(service.deleteAll()).toEqual({ success: true, data: { deleted: 2 } });
    await waitFor(async () => (await snapshotData(states)).every((data) => data === null));
    expect(await snapshotData(states)).toEqual([null, null]);

    await Promise.all(leases.map((lease) => lease.release()));
  });

  it('deletes orphaned keys and invalidates only their live mementos', async () => {
    service = await createService();
    const keys = [
      { mementoId: 'tasks.drawer', kind: 'task', key: 'keep' },
      { mementoId: 'tasks.drawer', kind: 'task', key: 'orphan' },
      { mementoId: 'projects.sidebar', kind: 'project', key: 'orphan' },
    ];
    const leases = keys.map((key) => service!.host.acquireState(key, 'value'));
    const states = await Promise.all(leases.map((lease) => lease.ready()));
    for (let index = 0; index < keys.length; index++) {
      await service.host.runMutation('save', {
        key: keys[index]!,
        input: { version: '1', data: '{}', updatedAt: index },
        mutationId: `save-orphans-${index}`,
      });
    }

    expect(service.deleteOrphans('task', ['keep'])).toEqual({
      success: true,
      data: { deleted: 1 },
    });
    await waitFor(async () => (await snapshotData([states[1]!]))[0] === null);
    expect(await snapshotData(states)).toEqual([
      { version: '1', data: '{}', updatedAt: 1_000 },
      null,
      { version: '1', data: '{}', updatedAt: 1_000 },
    ]);

    await Promise.all(leases.map((lease) => lease.release()));
  });
});

async function snapshotData(states: readonly LiveSource[]): Promise<unknown[]> {
  return await Promise.all(states.map(async (state) => (await state.snapshot()).data));
}

async function createService(): Promise<MementoService> {
  const handle = await mementosSqliteStore.openTemp();
  return new MementoService({
    persistence: new MementoPersistenceService(handle),
    scope: createScope({ label: 'memento-service-test' }),
    idleTtlMs: 0,
    now: () => 1_000,
  });
}
