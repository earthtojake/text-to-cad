import { hostRefSchema } from '@emdash/core/primitives/host/api';
import {
  activateWorkspaceErrorSchema,
  createWorkspaceErrorSchema,
  createWorktreeErrorSchema,
  deleteWorkspaceErrorSchema,
  deleteWorktreeErrorSchema,
  retryableLifecycleStepSchema,
  updateWorktreeErrorSchema,
  workspaceNotFoundErrorSchema,
  workspaceRecordSchema,
} from '@emdash/core/runtimes/workspace-registry/api';
import { runtimeResolveErrorSchema } from '@emdash/core/services/runtime-broker/api';
import { defineContract, fallible, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type { WorkspaceConfig, WorkspaceMirrorRow } from '@core/primitives/workspaces/api';

const hostInput = z.object({ host: hostRefSchema });
const workspaceKeyInput = hostInput.extend({ workspaceId: z.string().min(1) });

export const listWorkspacesInputSchema = z.object({
  scope: z.union([z.object({ host: hostRefSchema }), z.object({ projectId: z.string().min(1) })]),
  /** Serves the machines-page tombstones; live rows only by default. */
  includeUntracked: z.boolean().optional(),
});
export type ListWorkspacesInput = z.infer<typeof listWorkspacesInputSchema>;

export const workspaceRegistryDomain = 'workspaceRegistry' as const;

export const workspaceClaimErrorSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('workspace-identity-conflict'),
    path: z.string(),
    incomingId: z.string(),
    conflictingId: z.string(),
  }),
  z.object({ type: z.literal('workspace-tombstoned'), workspaceId: z.string() }),
]);

/**
 * The consolidated renderer workspace API (ADR 0005): list from the mirror, call any
 * lifecycle verb against any reachable host, untrack rows for hosts the desktop can no
 * longer reach. Verbs are 1:1 pass-throughs to the host registry contract plus the host
 * ref — the desktop mints UUIDs for the create verbs and fails fast with a typed
 * runtime-resolve error when the host is unreachable; nothing is queued, ever.
 */
export const workspaceRegistryWireContract = defineContract({
  /** Mirror rows (record + annotations + host ref); never touches the host. */
  listWorkspaces: procedure({
    input: listWorkspacesInputSchema,
    output: z.custom<WorkspaceMirrorRow[]>(),
  }),

  /**
   * Register an existing path; success registers/annotates the mirror row immediately
   * so links can attach without waiting for sync.
   */
  createWorkspace: fallible({
    input: hostInput.extend({
      path: z.string().min(1),
      config: z.custom<WorkspaceConfig>().optional(),
    }),
    data: workspaceRecordSchema,
    error: z.union([
      createWorkspaceErrorSchema,
      workspaceClaimErrorSchema,
      runtimeResolveErrorSchema,
    ]),
  }),

  /**
   * Create a worktree from a registered repository; success registers/annotates the
   * mirror row immediately. Progress is the records overlay via sync — no job objects.
   */
  createWorktree: fallible({
    input: hostInput.extend({
      repositoryId: z.string().min(1),
      branch: z.string().min(1),
      baseRef: z.string().min(1),
      path: z.string().min(1),
      preservePatterns: z.array(z.string()).optional(),
      publish: z.object({ remote: z.string().min(1) }).optional(),
      config: z.custom<WorkspaceConfig>().optional(),
    }),
    data: workspaceRecordSchema,
    error: z.union([
      createWorktreeErrorSchema,
      workspaceClaimErrorSchema,
      runtimeResolveErrorSchema,
    ]),
  }),

  activateWorkspace: fallible({
    input: workspaceKeyInput,
    data: workspaceRecordSchema,
    error: z.union([activateWorkspaceErrorSchema, runtimeResolveErrorSchema]),
  }),

  deactivateWorkspace: fallible({
    input: workspaceKeyInput,
    data: z.void(),
    error: z.union([workspaceNotFoundErrorSchema, runtimeResolveErrorSchema]),
  }),

  deleteWorkspace: fallible({
    input: workspaceKeyInput,
    data: z.void(),
    error: z.union([deleteWorkspaceErrorSchema, runtimeResolveErrorSchema]),
  }),

  deleteWorktree: fallible({
    input: workspaceKeyInput.extend({ deleteBranch: z.boolean().optional() }),
    data: z.void(),
    error: z.union([deleteWorktreeErrorSchema, runtimeResolveErrorSchema]),
  }),

  refresh: fallible({
    input: hostInput.extend({ workspaceId: z.string().min(1).optional() }),
    data: z.void(),
    error: z.union([workspaceNotFoundErrorSchema, runtimeResolveErrorSchema]),
  }),

  /**
   * Manual "Update now" for a PR checkout: fast-forwards the worktree to the
   * desktop-compiled `{ remote, sourceRef }` instruction (pr-workspace-model spec,
   * Staleness). The host never reads record fields for this — pre-model workspaces
   * update identically. Guard refusals (dirty, active sessions, diverged) come back
   * as distinct typed errors.
   */
  updateWorktree: fallible({
    input: workspaceKeyInput.extend({
      remote: z.string().min(1),
      sourceRef: z.string().min(1),
    }),
    data: z.void(),
    error: z.union([updateWorktreeErrorSchema, runtimeResolveErrorSchema]),
  }),

  /** Manual retry of a durably failed lifecycle step (copy-artifacts | push-branch). */
  retryStep: fallible({
    input: workspaceKeyInput.extend({ step: retryableLifecycleStepSchema }),
    data: workspaceRecordSchema,
    error: z.union([
      workspaceNotFoundErrorSchema,
      workspaceClaimErrorSchema,
      runtimeResolveErrorSchema,
    ]),
  }),

  /**
   * Desktop-only escape hatch for unreachable or identity-lost rows: a durable
   * tombstone sync never resurrects. Reachable-host removals go through the verbs.
   */
  untrackWorkspace: procedure({
    input: z.object({ workspaceId: z.string().min(1) }),
    output: z.void(),
  }),

  /**
   * Retry affordance for a pending deletion stopped by a terminal removal failure
   * (ADR 0006): durably advances the tombstone's attempt epoch — the recorded stop
   * goes inert on the row itself, surviving sync and restarts — and resets the
   * reconcile sweep's backoff so one fresh attempt runs now. No-op without a tombstone.
   */
  retryWorkspaceRemoval: procedure({
    input: z.object({ workspaceId: z.string().min(1) }),
    output: z.void(),
  }),

  /**
   * "Untrack anyway" affordance (ADR 0006): abandons the pending deletion — purges
   * the tombstoned mirror row client-side and keeps the host artifacts. The durable
   * untrack means sync never resurrects the row while the host record survives.
   */
  abandonWorkspaceRemoval: procedure({
    input: z.object({ workspaceId: z.string().min(1) }),
    output: z.void(),
  }),
});

export type WorkspaceRegistryWireContract = typeof workspaceRegistryWireContract;
