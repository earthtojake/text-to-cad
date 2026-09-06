import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import { fsWatchComponent, type fsWatchComponentConfigSchema } from './component';

type FsWatchWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof fsWatchComponent)['requirements'],
  z.infer<typeof fsWatchComponentConfigSchema>
>;

export type FsWatchWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
};

/** Spawn spec for the shared filesystem watcher worker. */
export function fsWatchWorkerSpec(
  input: FsWatchWorkerSpecInput
): readonly [typeof fsWatchComponent, FsWatchWorkerOptions] {
  return [
    fsWatchComponent,
    {
      name: 'fs-watch',
      executable: input.executable,
      env: input.env,
      dependencies: {},
      config: {},
    },
  ];
}
