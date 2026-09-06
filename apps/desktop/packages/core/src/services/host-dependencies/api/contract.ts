import {
  defineContract,
  fallible,
  liveJob,
  liveModel,
  liveState,
  mutation,
} from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  dependencyIdSchema,
  hostDependencyErrorSchema,
  hostDependencySelectionSchema,
  hostDependencySnapshotSchema,
  hostDependencyViewSchema,
  resolvedHostDependencySchema,
} from '#primitives/host-dependencies/api';
import {
  hostDependencyInputSchema,
  hostDependencyInstallBatchResultSchema,
  hostDependencyInstallRequestSchema,
  hostDependencyOperationProgressSchema,
} from './schemas';

export const hostDependencyResolverContract = defineContract({
  resolve: fallible({
    input: hostDependencyInputSchema,
    data: resolvedHostDependencySchema,
    error: hostDependencyErrorSchema,
  }),
});

export const hostDependenciesContract = defineContract({
  resolver: hostDependencyResolverContract,
  snapshot: liveModel({
    key: z.void().optional(),
    states: {
      current: liveState({ data: hostDependencySnapshotSchema }),
    },
    mutations: {
      setSelection: mutation({
        input: hostDependencyInputSchema.extend({ selection: hostDependencySelectionSchema }),
        data: hostDependencyViewSchema,
        error: hostDependencyErrorSchema,
      }),
      refresh: mutation({
        input: z.object({ id: dependencyIdSchema.optional() }).optional(),
        data: hostDependencySnapshotSchema,
        error: hostDependencyErrorSchema,
      }),
    },
  }),
  runSelfUpdateCommand: liveJob({
    input: hostDependencyInputSchema,
    progress: hostDependencyOperationProgressSchema,
    result: hostDependencyViewSchema,
    error: hostDependencyErrorSchema,
  }),
  runInstallCommand: liveJob({
    input: hostDependencyInstallRequestSchema.extend({
      commandKind: z.enum(['install', 'update']).optional(),
    }),
    progress: hostDependencyOperationProgressSchema,
    result: hostDependencyViewSchema,
    error: hostDependencyErrorSchema,
  }),
  runInstallBatch: liveJob({
    input: z.object({ requests: z.array(hostDependencyInstallRequestSchema).min(1) }),
    progress: hostDependencyOperationProgressSchema,
    result: hostDependencyInstallBatchResultSchema,
    error: hostDependencyErrorSchema,
  }),
});

export type HostDependencyResolverContract = typeof hostDependencyResolverContract;
export type HostDependenciesContract = typeof hostDependenciesContract;
