import { z } from 'zod';
import {
  dependencyIdSchema,
  hostDependencyViewResultSchema,
  installMethodSchema,
} from '#primitives/host-dependencies/api';

/** Input addressing a single dependency by id. */
export const hostDependencyInputSchema = z.object({ id: dependencyIdSchema });

export const hostDependencyInstallRequestSchema = hostDependencyInputSchema.extend({
  method: installMethodSchema.optional(),
  elevate: z.boolean().optional(),
});
export type HostDependencyInstallRequest = z.output<typeof hostDependencyInstallRequestSchema>;

export const hostDependencyInstallBatchResultSchema = z.record(
  dependencyIdSchema,
  hostDependencyViewResultSchema
);
export type HostDependencyInstallBatchResult = z.output<
  typeof hostDependencyInstallBatchResultSchema
>;

export const hostDependencyOperationProgressSchema = z.object({
  phase: z.enum(['resolving', 'running', 'refreshing']),
});
export type HostDependencyOperationProgress = z.output<
  typeof hostDependencyOperationProgressSchema
>;
