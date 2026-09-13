import type { ProvidedWireComponentRequirements } from '@emdash/wire/worker';
import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import { gitComponent, type gitComponentConfigSchema } from './component';
import { gitRuntimeEnv } from './non-interactive-env';

type GitWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof gitComponent)['requirements'],
  z.infer<typeof gitComponentConfigSchema>
>;

export type GitWorkerSpecInput = {
  executable: string;
  /** Base environment; the spec composes the non-interactive git env on top. */
  env: NodeJS.ProcessEnv;
  dependencies: ProvidedWireComponentRequirements<(typeof gitComponent)['requirements']>;
  /** Path to the git binary; defaults to PATH resolution inside the worker. */
  gitExecutable?: string;
};

/**
 * Spawn spec for the git runtime worker. Its own process receives the
 * non-interactive environment; each git subprocess resolves a fresh user
 * environment through the component dependency.
 */
export function gitWorkerSpec(
  input: GitWorkerSpecInput
): readonly [typeof gitComponent, GitWorkerOptions] {
  const env = gitRuntimeEnv(input.env);
  return [
    gitComponent,
    {
      name: 'git',
      executable: input.executable,
      env,
      dependencies: input.dependencies,
      config: {
        ...(input.gitExecutable ? { executable: input.gitExecutable } : {}),
      },
    },
  ];
}
