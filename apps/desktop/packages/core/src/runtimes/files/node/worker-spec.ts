import type { ProvidedWireComponentRequirements } from '@emdash/wire/worker';
import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import { filesComponent, type filesComponentConfigSchema } from './component';

type FilesWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof filesComponent)['requirements'],
  z.infer<typeof filesComponentConfigSchema>
>;

export type FilesWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
  dependencies: ProvidedWireComponentRequirements<(typeof filesComponent)['requirements']>;
  watchIgnore?: string[];
};

/** Spawn spec for the files runtime worker. */
export function filesWorkerSpec(
  input: FilesWorkerSpecInput
): readonly [typeof filesComponent, FilesWorkerOptions] {
  return [
    filesComponent,
    {
      name: 'files',
      executable: input.executable,
      env: input.env,
      dependencies: input.dependencies,
      config: input.watchIgnore ? { watchIgnore: input.watchIgnore } : {},
    },
  ];
}
