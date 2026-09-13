import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { gitContract } from '#runtimes/git/api';
import { createGitController } from '#runtimes/git/node/api/controller';
import { GitRuntime } from '#runtimes/git/node/git-runtime';
import { gitRuntimeEnv } from '#runtimes/git/node/non-interactive-env';
import { fsWatchContract } from '#services/fs-watch/api';
import { createProcessWatchServiceFromDependency } from '#services/fs-watch/node/process-watch-service';
import { hostDependencyResolverContract } from '#services/host-dependencies/api';
import { userShellEnvContract } from '#services/shell-env/api';

export const gitComponentConfigSchema = z.object({
  executable: z.string().min(1).optional(),
  idleTtlMs: z.number().nonnegative().optional(),
  aliasTtlMs: z.number().nonnegative().optional(),
  maxFileContentStates: z.number().nonnegative().optional(),
});

export const gitComponent = defineWireComponent({
  id: 'git',
  contract: gitContract,
  requirements: {
    watcher: requireContract(fsWatchContract),
    hostDependencies: requireContract(hostDependencyResolverContract),
    userEnv: requireContract(userShellEnvContract),
  },
  configSchema: gitComponentConfigSchema,
  create: ({ config, dependencies, instance, logger, scope }) => {
    const watcher = createProcessWatchServiceFromDependency({
      client: dependencies.watcher,
      logger,
      scope,
    });
    const runtime = new GitRuntime({
      watcher,
      executable: config.executable,
      env: async () => gitRuntimeEnv(await dependencies.userEnv.get()),
      idleTtlMs: config.idleTtlMs,
      aliasTtlMs: config.aliasTtlMs,
      maxFileContentStates: config.maxFileContentStates,
      onError: (context, error) => logger.warn(context, { error }),
    });
    scope.add(() => runtime.dispose());

    return instance({
      scope,
      controller: createGitController(runtime),
    });
  },
});
