import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ConfigModel, readConfigFile } from './config-model';

describe('readConfigFile', () => {
  let dir: string;

  beforeEach(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), 'config-model-'));
  });

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  const parse = (content: string): { success: boolean; data: { value?: string } } => {
    try {
      return { success: true, data: JSON.parse(content) as { value?: string } };
    } catch {
      return { success: false, data: {} };
    }
  };

  it('treats a missing file as the empty default without a parse error', async () => {
    const entry = await readConfigFile(path.join(dir, 'absent.json'), parse);
    expect(entry).toEqual({ data: {}, parseError: false });
  });

  it('parses a present file', async () => {
    const file = path.join(dir, 'config.json');
    await writeFile(file, JSON.stringify({ value: 'x' }));
    const entry = await readConfigFile(file, parse);
    expect(entry).toEqual({ data: { value: 'x' }, parseError: false });
  });

  it('flags a present-but-broken file as a parse error with the lenient default', async () => {
    const file = path.join(dir, 'config.json');
    await writeFile(file, '{nope');
    const entry = await readConfigFile(file, parse);
    expect(entry).toEqual({ data: {}, parseError: true });
  });
});

describe('ConfigModel', () => {
  it('caches entries per key and reports them via get', async () => {
    const model = new ConfigModel<{ n: number }>({
      read: async (key) => ({ n: key.length }),
    });
    expect(model.get('ab')).toBeUndefined();
    await model.refresh('ab', 'ab');
    expect(model.get('ab')).toEqual({ n: 2 });
  });

  it('coalesces concurrent refreshes for one key', async () => {
    let reads = 0;
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const model = new ConfigModel<{ n: number }>({
      read: async () => {
        reads += 1;
        await gate;
        return { n: reads };
      },
    });
    const first = model.refresh('a', 'a');
    const second = model.refresh('a', 'a');
    release();
    expect(await first).toEqual({ n: 1 });
    expect(await second).toEqual({ n: 1 });
    expect(reads).toBe(1);
  });

  it('fires onChanged only when the entry actually changed', async () => {
    const contents = new Map<string, number>([['a', 1]]);
    const events: Array<{
      key: string;
      entry: { n: number };
      previous: { n: number } | undefined;
    }> = [];
    const model = new ConfigModel<{ n: number }>({
      read: async (key) => ({ n: contents.get(key) ?? 0 }),
      onChanged: (key, entry, previous) => {
        events.push({ key, entry, previous });
      },
    });
    await model.refresh('a', 'a');
    await model.refresh('a', 'a');
    contents.set('a', 2);
    await model.refresh('a', 'a');
    expect(events).toEqual([
      { key: 'a', entry: { n: 1 }, previous: undefined },
      { key: 'a', entry: { n: 2 }, previous: { n: 1 } },
    ]);
  });

  it('delete drops the cached entry so the next refresh reports a fresh change', async () => {
    const events: string[] = [];
    const model = new ConfigModel<{ n: number }>({
      read: async () => ({ n: 1 }),
      onChanged: (key) => {
        events.push(key);
      },
    });
    await model.refresh('a', 'a');
    model.delete('a');
    expect(model.get('a')).toBeUndefined();
    await model.refresh('a', 'a');
    expect(events).toEqual(['a', 'a']);
  });

  it('delete prevents an in-flight refresh from restoring a stale entry', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const events: string[] = [];
    const model = new ConfigModel<{ n: number }>({
      read: async () => {
        await gate;
        return { n: 1 };
      },
      onChanged: (key) => {
        events.push(key);
      },
    });

    const refreshing = model.refresh('a', 'a');
    model.delete('a');
    release();
    await refreshing;

    expect(model.get('a')).toBeUndefined();
    expect(events).toEqual([]);
  });

  it('after dispose, refreshes still resolve but never store or fire callbacks', async () => {
    const events: string[] = [];
    const model = new ConfigModel<{ n: number }>({
      read: async () => ({ n: 1 }),
      onChanged: (key) => {
        events.push(key);
      },
    });
    model.dispose();
    const entry = await model.refresh('a', 'a');
    expect(entry).toEqual({ n: 1 });
    expect(model.get('a')).toBeUndefined();
    expect(events).toEqual([]);
  });
});
