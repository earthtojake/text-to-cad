import type { Logger } from '@emdash/shared/logger';
import { createController } from '@emdash/wire/rpc';
import { defineWireComponent } from '@emdash/wire/worker';
import { z } from 'zod';
import type { IExecutionContext } from '#primitives/exec/api';
import {
  hostDependencyDefinitionSchema,
  type HostDependencyError,
} from '#primitives/host-dependencies/api';
import type { KeyValueStore } from '#primitives/kv/api';
import { hostDependenciesContract } from '#services/host-dependencies/api';
import { HostDependenciesRuntime } from './runtime';

export const hostDependenciesComponentConfigSchema = z.object({
  hostId: z.string().min(1),
  definitions: z.array(hostDependencyDefinitionSchema),
});

export type HostDependenciesComponentConfig = z.output<
  typeof hostDependenciesComponentConfigSchema
>;

export type CreateHostDependenciesComponentOptions = {
  store: KeyValueStore;
  exec: IExecutionContext;
  logger?: Logger;
};

export function createHostDependenciesComponent(options: CreateHostDependenciesComponentOptions) {
  return defineWireComponent({
    id: 'host-dependencies',
    contract: hostDependenciesContract,
    requirements: {},
    configSchema: hostDependenciesComponentConfigSchema,
    create: ({ config, instance, scope }) => {
      const exec = options.exec;
      scope.add(() => exec.dispose());
      const runtime = new HostDependenciesRuntime({
        hostId: config.hostId,
        definitions: config.definitions,
        store: options.store,
        exec,
        logger: options.logger,
      });
      scope.add(() => runtime.dispose());

      return instance({
        scope,
        controller: createHostDependenciesController(runtime),
      });
    },
  });
}

const toCommandFailedError = (error: unknown): HostDependencyError => ({
  type: 'command-failed',
  message: error instanceof Error ? error.message : String(error),
  output: '',
});

export function createHostDependenciesController(runtime: HostDependenciesRuntime) {
  return createController(hostDependenciesContract, {
    resolver: {
      resolve: ({ id }) => runtime.resolve(id),
    },
    snapshot: runtime.liveHost(),
    runSelfUpdateCommand: {
      run: ({ id }, ctx) => runtime.runSelfUpdateCommand(id, ctx),
      toError: toCommandFailedError,
    },
    runInstallCommand: {
      run: ({ id, method, elevate, commandKind }, ctx) =>
        runtime.runInstallCommand(id, method, ctx, { elevate, commandKind }),
      toError: toCommandFailedError,
    },
    runInstallBatch: {
      run: ({ requests }, ctx) => runtime.runInstallBatch(requests, ctx),
      toError: toCommandFailedError,
    },
  });
}
