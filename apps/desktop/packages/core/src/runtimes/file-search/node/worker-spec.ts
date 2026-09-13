import type { ProvidedWireComponentRequirements } from '@emdash/wire/worker';
import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import { fileSearchComponent, type fileSearchComponentConfigSchema } from './component';

type FileSearchWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof fileSearchComponent)['requirements'],
  z.infer<typeof fileSearchComponentConfigSchema>
>;

export type FileSearchWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
  dependencies: ProvidedWireComponentRequirements<(typeof fileSearchComponent)['requirements']>;
  databasePath: string;
  ripgrepPath?: string;
};

/** Spawn spec for the file-search runtime worker. */
export function fileSearchWorkerSpec(
  input: FileSearchWorkerSpecInput
): readonly [typeof fileSearchComponent, FileSearchWorkerOptions] {
  return [
    fileSearchComponent,
    {
      name: 'file-search',
      executable: input.executable,
      env: input.env,
      dependencies: input.dependencies,
      config: {
        databasePath: input.databasePath,
        ...(input.ripgrepPath ? { ripgrepPath: input.ripgrepPath } : {}),
      },
    },
  ];
}
