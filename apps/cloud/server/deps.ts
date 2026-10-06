// Real dependencies from the environment, for the node and Vercel entries.
import { createAuth } from './auth.ts';
import { systemClock } from './clock.ts';
import { loadConfig, type Env } from './config.ts';
import { openDb } from './db/index.ts';
import { createSandbox } from './sandbox/index.ts';
import type { Deps } from './service.ts';
import { createFsStore, createR2Store, type ObjectStore } from './store.ts';

export async function depsFromEnv(env: Env = process.env, extra: Pick<Deps, 'background' | 'log'> = {}): Promise<Deps> {
  const config = loadConfig(env);
  const db = await openDb(config.db);
  const store: ObjectStore = config.storage.kind === 'r2' ? createR2Store(config.storage) : createFsStore(config.storage.dir);
  const clock = systemClock;
  return {
    config,
    db,
    store,
    sandbox: createSandbox(config),
    auth: createAuth({ config, db, clock }),
    clock,
    ...extra,
  };
}
