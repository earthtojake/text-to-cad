import { waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { defineContract, liveLog } from '../../api/define';
import { createTestWire } from '../../testing';
import { LiveLogSource } from '../log';
import { createLiveLogReplicaCache } from './log';

const api = defineContract({
  output: liveLog({ key: z.object({ id: z.string() }) }),
});

describe('createLiveLogReplicaCache', () => {
  it('seeds retained text and passes through appends under local cursors', async () => {
    const key = { id: 'session' };
    const log = new LiveLogSource({ generation: 1000 });
    log.append('seed\n');
    const contractClient = createTestWire(api, { output: () => log }).client;

    const replica = createLiveLogReplicaCache(api.output, contractClient.output);
    const lease = replica.acquire(key);
    const output = await lease.ready();
    const appends: string[] = [];
    output.onAppend((chunk) => appends.push(chunk));

    expect(output.text()).toBe('seed\n');
    log.append('next\n');
    await waitFor(() => appends.length === 1);

    expect(appends).toEqual(['next\n']);
    expect((await output.snapshot()).data.text).toBe('seed\nnext\n');

    await lease.release();
    await replica.dispose();
  });

  it('writes through to a custom log store', async () => {
    const key = { id: 'session' };
    const log = new LiveLogSource({ generation: 1000 });
    log.append('seed');
    const contractClient = createTestWire(api, { output: () => log }).client;
    let text = '';

    const replica = createLiveLogReplicaCache(api.output, contractClient.output, {
      store: () => ({
        reset: (data) => {
          text = data.text;
        },
        append: (chunk) => {
          text += chunk;
        },
        text: () => text,
      }),
    });
    const lease = replica.acquire(key);
    const output = await lease.ready();

    expect(output.text()).toBe('seed');
    log.append('\nnext');
    await waitFor(() => output.text() === 'seed\nnext');

    await lease.release();
    await replica.dispose();
  });

  it('supports write-only log sinks without readable text', async () => {
    const key = { id: 'session' };
    const log = new LiveLogSource({ generation: 1000 });
    log.append('seed');
    const contractClient = createTestWire(api, { output: () => log }).client;
    const writes: string[] = [];

    const replica = createLiveLogReplicaCache(api.output, contractClient.output, {
      store: () => ({
        reset: (data) => {
          writes.push(`reset:${data.text}`);
        },
        append: (chunk) => {
          writes.push(`append:${chunk}`);
        },
      }),
    });
    const lease = replica.acquire(key);
    const output = await lease.ready();

    expect(() => output.text()).toThrow('write-only LogSink');
    log.append('\nnext');
    await waitFor(() => writes.length === 2);
    expect(writes).toEqual(['reset:seed', 'append:\nnext']);

    await lease.release();
    await replica.dispose();
  });

  it('serves downstream clients from the local log buffer', async () => {
    const key = { id: 'session' };
    const log = new LiveLogSource({ generation: 1000 });
    const upstream = createTestWire(api, { output: () => log }).client;
    const replica = createLiveLogReplicaCache(api.output, upstream.output);
    const downstream = createTestWire(api, { output: replica }).client;

    const handle = downstream.output.handle(key);
    const updates: string[] = [];
    const detach = await handle.attach((update) => {
      updates.push((update.delta as { chunk: string }).chunk);
    });
    await handle.snapshot();
    log.append('served\n');
    await waitFor(() => updates.length === 1);

    expect((await handle.snapshot()).data.text).toBe('served\n');

    detach();
    await replica.dispose();
  });
});
