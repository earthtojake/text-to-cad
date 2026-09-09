import type { ProvidedWireComponentRequirements } from '@emdash/wire/worker';
import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import {
  workspaceRegistryComponent,
  type workspaceRegistryComponentConfigSchema,
} from './component';

type WorkspaceRegistryWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof workspaceRegistryComponent)['requirements'],
  z.infer<typeof workspaceRegistryComponentConfigSchema>
>;

export type WorkspaceRegistryWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
  dependencies: ProvidedWireComponentRequirements<
    (typeof workspaceRegistryComponent)['requirements']
  >;
  databasePath: string;
};

/**
 * Spawn spec for the workspace registry worker. The registry owns its database
 * exclusively (ADR 0005); the watcher feeds its freshness scheduler; the session
 * runtimes are deactivateWorkspace's kill-sessions plane. Default supervision
 * (restart on failure) is deliberate: a durable index should come back; its
 * runtime overlay is ephemeral by design. The 3s shutdown grace lets it close
 * its database cleanly before the host escalates.
 */
export function workspaceRegistryWorkerSpec(
  input: WorkspaceRegistryWorkerSpecInput
): readonly [typeof workspaceRegistryComponent, WorkspaceRegistryWorkerOptions] {
  return [
    workspaceRegistryComponent,
    {
      name: 'workspace-registry',
      executable: input.executable,
      env: input.env,
      dependencies: input.dependencies,
      config: { databasePath: input.databasePath },
      shutdownGraceMs: 3_000,
    },
  ];
}
