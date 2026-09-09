import path from 'node:path';
import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { fileSearchContract } from '#runtimes/file-search/api';
import { createFileSearchController } from '#runtimes/file-search/node/api/controller';
import { FileSearchRuntime } from '#runtimes/file-search/node/file-search-runtime';
import { fsWatchContract } from '#services/fs-watch/api';
import { createProcessWatchServiceFromDependency } from '#services/fs-watch/node/process-watch-service';
import { userShellEnvContract } from '#services/shell-env/api';
import { fileSearchStore } from './storage/store';

export const fileSearchComponentConfigSchema = z.object({
  databasePath: z
    .string()
    .min(1)
    .refine((value) => value === ':memory:' || path.isAbsolute(value), {
      message: 'File-search database path must be absolute or :memory:',
    }),
  ripgrepPath: z.string().min(1).optional(),
  maxConcurrentScans: z.number().int().positive().optional(),
  maxConcurrentContentSearches: z.number().int().positive().optional(),
});

export type FileSearchComponentConfig = z.infer<typeof fileSearchComponentConfigSchema>;

export const fileSearchComponent = defineWireComponent({
  id: 'file-search',
  contract: fileSearchContract,
  requirements: {
    watcher: requireContract(fsWatchContract),
    userEnv: requireContract(userShellEnvContract),
  },
  configSchema: fileSearchComponentConfigSchema,
  create: ({ config, dependencies, instance, logger, scope }) => {
    const handle = fileSearchStore.open(config.databasePath);
    scope.add(() => handle.close());

    const watcher = createProcessWatchServiceFromDependency({
      client: dependencies.watcher,
      logger,
      scope,
    });
    const runtime = new FileSearchRuntime({
      handle,
      watcher,
      env: () => dependencies.userEnv.get(),
      ripgrepPath: config.ripgrepPath,
      maxConcurrentScans: config.maxConcurrentScans,
      maxConcurrentContentSearches: config.maxConcurrentContentSearches,
      onError: (context, error) => logger.warn(context, { error }),
    });
    scope.add(() => runtime.dispose());

    return instance({
      scope,
      controller: createFileSearchController(runtime),
    });
  },
});
