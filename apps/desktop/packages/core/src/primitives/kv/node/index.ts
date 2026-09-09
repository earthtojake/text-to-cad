import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { ok, type Result, type Serializable } from '@emdash/shared';
import { keyValueIoError, type KeyValueStore, type KeyValueStoreError } from '../api';

export type JsonFileKeyValueStoreOptions = {
  path: string;
};

export function createJsonFileKeyValueStore(options: JsonFileKeyValueStoreOptions): KeyValueStore {
  let loaded: Record<string, Serializable> | null = null;
  let writeQueue = Promise.resolve();

  async function load(): Promise<Result<Record<string, Serializable>, KeyValueStoreError>> {
    if (loaded) return ok(loaded);
    try {
      const text = await readFile(options.path, 'utf8');
      const parsed = JSON.parse(text) as Record<string, Serializable>;
      loaded = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
      return ok(loaded);
    } catch (error) {
      const err = error as NodeJS.ErrnoException;
      if (err.code === 'ENOENT') {
        loaded = {};
        return ok(loaded);
      }
      return { success: false, error: keyValueIoError(error, 'Failed to read KV file') };
    }
  }

  async function flush(): Promise<Result<void, KeyValueStoreError>> {
    const data = loaded ?? {};
    const tmpPath = `${options.path}.${process.pid}.tmp`;
    try {
      await mkdir(dirname(options.path), { recursive: true });
      await writeFile(tmpPath, JSON.stringify(data, null, 2), 'utf8');
      await rename(tmpPath, options.path);
      return ok();
    } catch (error) {
      return { success: false, error: keyValueIoError(error, 'Failed to write KV file') };
    }
  }

  function enqueueWrite(mutator: () => void): Promise<Result<void, KeyValueStoreError>> {
    const run = async () => {
      const state = await load();
      if (!state.success) return state;
      mutator();
      return flush();
    };
    const result = writeQueue.then(run, run);
    writeQueue = result.then(
      () => undefined,
      () => undefined
    );
    return result;
  }

  return {
    async get(key) {
      const state = await load();
      if (!state.success) return state;
      return ok(state.data[key] ?? null);
    },
    set(key, value) {
      return enqueueWrite(() => {
        (loaded ??= {})[key] = value;
      });
    },
    delete(key) {
      return enqueueWrite(() => {
        delete (loaded ??= {})[key];
      });
    },
    async getAll() {
      const state = await load();
      if (!state.success) return state;
      return ok({ ...state.data });
    },
  };
}
