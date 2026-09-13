import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { filesContract } from '#runtimes/files/api';
import { createFilesController } from '#runtimes/files/node/api/controller';
import { FilesRuntime } from '#runtimes/files/node/files-runtime';
import { fsWatchContract } from '#services/fs-watch/api';
import { createProcessWatchServiceFromDependency } from '#services/fs-watch/node/process-watch-service';

export const filesComponentConfigSchema = z.object({
  idleTtlMs: z.number().nonnegative().optional(),
  maxContentBytes: z.number().nonnegative().optional(),
  watchIgnore: z.array(z.string()).optional(),
});

export const filesComponent = defineWireComponent({
  id: 'files',
  contract: filesContract,
  requirements: {
    watcher: requireContract(fsWatchContract),
  },
  configSchema: filesComponentConfigSchema,
  create: ({ config, dependencies, instance, logger, scope }) => {
    const watcher = createProcessWatchServiceFromDependency({
      client: dependencies.watcher,
      logger,
      scope,
    });
    const runtime = new FilesRuntime({
      watcher,
      watchIgnoreGlobs: config.watchIgnore,
      idleTtlMs: config.idleTtlMs,
      maxContentBytes: config.maxContentBytes,
      onError: (context, error) => logger.warn(context, { error }),
    });
    scope.add(() => runtime.dispose());

    return instance({
      scope,
      controller: createFilesController(runtime),
    });
  },
});
