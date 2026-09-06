import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { terminalsContract } from '#runtimes/terminals/api';
import { NodeExecutionContext } from '#services/exec/api';
import { createNodeTerminalShellResolver, NodePtySpawner } from '#services/pty/node';
import { idlePolicyConfigSchema } from '#services/session-lifecycle/api';
import { userShellEnvContract } from '#services/shell-env/api';
import { createTerminalsController } from './api/controller';
import { TerminalsRuntime } from './runtime/runtime';

export const terminalsComponentConfigSchema = z.object({
  lifecycle: z
    .object({
      terminal: idlePolicyConfigSchema.optional(),
      sweepIntervalMs: z.number().int().positive().optional(),
    })
    .optional(),
});

export const terminalsComponent = defineWireComponent({
  id: 'terminals',
  contract: terminalsContract,
  requirements: {
    userEnv: requireContract(userShellEnvContract),
  },
  configSchema: terminalsComponentConfigSchema,
  create: ({ config, dependencies, instance, logger, scope }) => {
    const runtime = new TerminalsRuntime({
      spawner: new NodePtySpawner(),
      userEnv: () => dependencies.userEnv.get(),
      createExecutionContext: (env) => new NodeExecutionContext({ env }),
      scope,
      lifecycle: config.lifecycle,
      createShellResolver: (env) => createNodeTerminalShellResolver({ env }),
      logger,
    });
    scope.add(() => runtime.dispose());

    return instance({
      scope,
      controller: createTerminalsController(runtime),
    });
  },
});
