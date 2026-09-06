import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { NodePtySpawner } from '#services/pty/node';
import { userShellEnvContract } from '#services/shell-env/api';
import { scriptsContract } from '../api/contract';
import { createScriptsController } from './api/controller';
import { ScriptsRuntime } from './runtime';

/** The scripts worker: a strict execution plane for already-resolved inputs. */
export const scriptsComponentConfigSchema = z.object({});

export const scriptsComponent = defineWireComponent({
  id: 'scripts',
  contract: scriptsContract,
  requirements: {
    userEnv: requireContract(userShellEnvContract),
  },
  configSchema: scriptsComponentConfigSchema,
  create: ({ dependencies, instance, logger, scope }) => {
    const runtime = new ScriptsRuntime({
      spawner: new NodePtySpawner(),
      userEnv: () => dependencies.userEnv.get(),
      logger,
    });
    scope.add(() => runtime.dispose());

    return instance({
      scope,
      controller: createScriptsController(runtime),
    });
  },
});
