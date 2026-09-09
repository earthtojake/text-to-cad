import { defineContract, fallible, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  activateWorkspaceErrorSchema,
  createWorkspaceErrorSchema,
  createWorktreeErrorSchema,
  deleteWorkspaceErrorSchema,
  deleteWorktreeErrorSchema,
  measureUsageErrorSchema,
  runScriptErrorSchema,
  updateWorktreeErrorSchema,
  workspaceNotFoundErrorSchema,
} from './errors';
import {
  activateWorkspaceInputSchema,
  createWorkspaceInputSchema,
  createWorktreeInputSchema,
  deactivateWorkspaceInputSchema,
  deleteWorkspaceInputSchema,
  deleteWorktreeInputSchema,
  getProjectConfigInputSchema,
  importLegacyLifecycleSettingsInputSchema,
  measureUsageInputSchema,
  patchPersonalProjectConfigInputSchema,
  projectConfigStateSchema,
  refreshWorkspacesInputSchema,
  retryStepInputSchema,
  runScriptInputSchema,
  updateWorktreeInputSchema,
  workspaceRecordSchema,
  workspaceRecordsSchema,
  workspaceUsageSchema,
} from './schemas';

/**
 * The host workspace registry (ADR 0005): a durable, sole-writer index of registered
 * paths plus host-computed observations. The filesystem stays the source of truth — the
 * registry observes it and never converges the world toward a record. Lifecycle verbs
 * are plain fail-fast RPCs; no outbox, no durable operations, no job objects. Progress
 * and current state are read from `records`, which merges durable rows with the
 * in-memory runtime overlay.
 */
export const workspaceRegistryContract = defineContract({
  /**
   * Sole read path. Full map on subscribe; durable records merged with the in-memory
   * runtime overlay; republished on every registry mutation, overlay change, and scan
   * result. Desktops apply every delivery as a full snapshot.
   */
  records: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: workspaceRecordsSchema }),
    },
  }),

  /** Resolved personal, team, host, and built-in config for one workspace. */
  projectConfig: liveModel({
    key: getProjectConfigInputSchema,
    states: {
      current: liveState({ data: projectConfigStateSchema }),
    },
  }),

  /** Resolves one workspace through personal, team, host, and built-in layers. */
  getProjectConfig: fallible({
    input: getProjectConfigInputSchema,
    data: projectConfigStateSchema,
    error: workspaceNotFoundErrorSchema,
  }),

  /**
   * Write-through consistency barrier for a known `.emdash.json` write. Rereads the
   * exact registered workspace path and publishes the refreshed project-config model
   * before returning.
   */
  refreshProjectConfig: fallible({
    input: getProjectConfigInputSchema,
    data: projectConfigStateSchema,
    error: workspaceNotFoundErrorSchema,
  }),

  /** Sole write path for repository-owned personal lifecycle settings. */
  patchPersonalProjectConfig: fallible({
    input: patchPersonalProjectConfigInputSchema,
    data: projectConfigStateSchema,
    error: workspaceNotFoundErrorSchema,
  }),

  /** One-time, only-if-absent import of legacy desktop lifecycle settings. */
  importLegacyLifecycleSettings: fallible({
    input: importLegacyLifecycleSettingsInputSchema,
    data: projectConfigStateSchema,
    error: workspaceNotFoundErrorSchema,
  }),

  /**
   * Register an existing path. Kind is host-detected; registering a worktree of an
   * unregistered repository auto-registers the parent (adopted). Replay: same id + same
   * path is a no-op success; a different path under the same id is an
   * immutable-field-mismatch; the same path under a different id returns the
   * canonical existing record as success.
   */
  createWorkspace: fallible({
    input: createWorkspaceInputSchema,
    data: workspaceRecordSchema,
    error: createWorkspaceErrorSchema,
  }),

  /**
   * Creates a worktree from a repository spec as one plain RPC: registers the record
   * immediately (outcome 'started'), executes the foreground pipeline inspect →
   * resolve-base → add-worktree → verify under an exclusive per-repository claim
   * (concurrent same-repo calls wait, never error), and returns at agent-spawnable.
   * Artifact cloning, branch pushing, and ref freshening continue as background steps
   * with durable per-step statuses on the record, outside the repository claim.
   * Progress is the records overlay — no job objects. Replay by id + identical spec:
   * succeeded → no-op (incomplete background steps re-run); failed/interrupted →
   * re-execute; divergent spec → typed mismatch.
   */
  createWorktree: fallible({
    input: createWorktreeInputSchema,
    data: workspaceRecordSchema,
    error: createWorktreeErrorSchema,
  }),

  /**
   * Manual retry of a durably failed lifecycle step (copy-artifacts | push-branch).
   * One fresh attempt; the outcome lands on the record's lifecycle section. Only a
   * failed step re-runs — anything else is a no-op returning the current record.
   */
  retryStep: fallible({
    input: retryStepInputSchema,
    data: workspaceRecordSchema,
    error: workspaceNotFoundErrorSchema,
  }),

  /**
   * Manual/retry lifecycle-script run: the registry builds the request from its
   * record (facts, default timeout) and starts it on the scripts runtime — clients
   * never resolve env, settings, or shellSetup themselves. The run is detached and
   * lands in the timeline through observation like every other run; a same-script
   * start while one is running is rejected (stop it first).
   */
  runScript: fallible({
    input: runScriptInputSchema,
    data: z.void(),
    error: runScriptErrorSchema,
  }),

  /**
   * Returns when the prepare script completes (the session-gating point); setup runs
   * after, concurrent with sessions; run waits on setup success. Script failures —
   * prepare included — surface as notices in the runtime overlay and never fail the
   * verb. Activation is ephemeral: it lives in the overlay and dies with the daemon;
   * only lastActivatedAt persists, as an observation. Re-activating an active
   * workspace is a no-op success.
   */
  activateWorkspace: fallible({
    input: activateWorkspaceInputSchema,
    data: workspaceRecordSchema,
    error: activateWorkspaceErrorSchema,
  }),

  /**
   * The sole owner of session-plane shutdown (ADR 0005, superseding ADR 0003): kills
   * every in-flight lifecycle run, awaits its cancelled settlement, runs teardown
   * time-boxed and non-fatal, then kills the workspace's remaining sessions. A failed
   * or hanging teardown becomes a notice, never a verb error.
   * Idempotent on inactive workspaces: teardown runs at most once per activation.
   */
  deactivateWorkspace: fallible({
    input: deactivateWorkspaceInputSchema,
    data: z.void(),
    error: workspaceNotFoundErrorSchema,
  }),

  /**
   * Deactivate-if-active + unregister. Never touches disk, valid on every kind.
   * Idempotent: an absent id succeeds. A failing teardown is a removal-stage failure
   * (ADR 0006): recorded durably as lastRemovalAttempt before the error returns; the
   * record stays registered so the delete is retryable.
   */
  deleteWorkspace: fallible({
    input: deleteWorkspaceInputSchema,
    data: z.void(),
    error: deleteWorkspaceErrorSchema,
  }),

  /**
   * Deactivate (sessions + teardown) + force-remove the worktree artifact (+ branch when
   * asked) + unregister — one call that leaves nothing behind. Worktree records only.
   * No host-side dirty/unpushed refusals: informed confirmation is the client's job from
   * mirror observations; the host executes what it is told. Idempotent: an absent id
   * succeeds, which is what makes an external tombstone-and-reconcile sweep safe.
   * Failures (teardown included, as a removal stage) are recorded durably on the
   * record as lastRemovalAttempt — stage, host-decided class, message — before the
   * error returns; the return itself is loop control, never UI truth (ADR 0006).
   */
  deleteWorktree: fallible({
    input: deleteWorktreeInputSchema,
    data: z.void(),
    error: deleteWorktreeErrorSchema,
  }),

  /**
   * Fast-forwards a worktree's checkout to `sourceRef` fetched from `remote` — the
   * manual "Update now" half of the staleness model, sharing its guarded executor with
   * the host ref-follow loop. Instruction-as-input: the host never reads the record's
   * `gitSetup`, so pre-model workspaces update identically. Guards run under the
   * per-worktree writer lock — dirty worktrees, live sessions, and diverged branches
   * refuse with distinct errors and nothing moves. A success writes nothing durable;
   * the post-mutation rescan feeds the observation.
   */
  updateWorktree: fallible({
    input: updateWorktreeInputSchema,
    data: z.void(),
    error: updateWorktreeErrorSchema,
  }),

  /**
   * On-demand git-aware disk observation, joining the registry's other per-workspace
   * observations: exclusive total bytes plus reclaimable git-ignored artifact bytes
   * (`git clean -ndX` roots). Id-keyed like every registry verb — the path resolves
   * from the record, never from the client.
   */
  measureUsage: fallible({
    input: measureUsageInputSchema,
    data: workspaceUsageSchema,
    error: measureUsageErrorSchema,
  }),

  /**
   * Explicit freshness verb: rescans one workspace (or the whole host), reconciling the
   * registry with the disk — adoption/un-adoption, missing flips, admin-name relinks —
   * and recomputing git observations. Results arrive through `records`.
   */
  refresh: fallible({
    input: refreshWorkspacesInputSchema,
    data: z.void(),
    error: workspaceNotFoundErrorSchema,
  }),
});

export type WorkspaceRegistryContract = typeof workspaceRegistryContract;
