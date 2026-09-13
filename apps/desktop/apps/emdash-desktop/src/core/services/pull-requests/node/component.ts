import path from 'node:path';
import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { githubAuthContract, pullRequestsContract } from '../api';
import { PullRequestService } from './pull-request-service';
import { PullRequestStore, pullRequestSqliteStore } from './store';
import { createPullRequestsWireController } from './wire-controller';

export const pullRequestsComponentConfigSchema = z.object({
  databasePath: z
    .string()
    .min(1)
    .refine((value) => value === ':memory:' || path.isAbsolute(value), {
      message: 'Pull-request database path must be absolute or :memory:',
    }),
  incrementalIntervalMs: z.number().int().positive().optional(),
  prSyncMaxCount: z.number().int().positive().optional(),
  archiveAgeMonths: z.number().int().positive().optional(),
});

export type PullRequestsComponentConfig = z.infer<typeof pullRequestsComponentConfigSchema>;

export const pullRequestsComponent = defineWireComponent({
  id: 'pull-requests',
  contract: pullRequestsContract,
  requirements: {
    githubAuth: requireContract(githubAuthContract),
  },
  configSchema: pullRequestsComponentConfigSchema,
  create: ({ config, dependencies, instance, logger, scope }) => {
    const handle = pullRequestSqliteStore.open(config.databasePath);
    scope.add(() => handle.close());
    const service = new PullRequestService({
      store: new PullRequestStore(handle),
      githubAuth: dependencies.githubAuth,
      scope,
      logger,
      incrementalIntervalMs: config.incrementalIntervalMs,
      maxSyncCount: config.prSyncMaxCount,
      archiveAgeMonths: config.archiveAgeMonths,
    });
    return instance({
      scope,
      controller: createPullRequestsWireController(service),
    });
  },
});
