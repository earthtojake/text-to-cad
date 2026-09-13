import { z } from 'zod';

/**
 * Keyed by workspace id (convention 5) — the registry resolves the path from its own
 * record; clients never hand it a path.
 */
export const measureUsageInputSchema = z.object({
  workspaceId: z.string().min(1),
});
export type MeasureUsageInput = z.infer<typeof measureUsageInputSchema>;

/** A non-fatal per-path measurement failure (unreadable directory, vanished file). */
export const workspaceUsageErrorSchema = z.object({
  path: z.string(),
  message: z.string(),
});
export type WorkspaceUsageError = z.infer<typeof workspaceUsageErrorSchema>;

/** The git-aware disk observation for one workspace. */
export const workspaceUsageSchema = z.object({
  /** Exclusive disk bytes for the workspace tree. */
  totalBytes: z.number().int().nonnegative(),
  /** Disk bytes attributable to git-ignored artifacts (reclaimable). */
  artifactBytes: z.number().int().nonnegative(),
  errors: z.array(workspaceUsageErrorSchema),
});
export type WorkspaceUsage = z.infer<typeof workspaceUsageSchema>;
