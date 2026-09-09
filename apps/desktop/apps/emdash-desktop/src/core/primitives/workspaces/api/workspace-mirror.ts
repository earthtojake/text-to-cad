import type { HostRef } from '@emdash/core/primitives/host/api';
import type { WorkspaceConfig } from './workspace-config';
import type {
  WorkspaceCreateOutcome,
  WorkspaceObservedGit,
  WorkspaceRemovalAttempt,
  WorkspaceRuntimeOverlay,
  WorkspaceScriptOutcomes,
} from './workspace-registry-observations';

/**
 * A desktop mirror row of a host registry record (ADR 0005), as served to the renderer:
 * host-owned observations plus the client-owned `config` annotation and the decoded
 * host ref. `host` is null when identity is lost (the row's SSH connection was deleted);
 * such rows surface the loss and refuse host-mutating flows.
 */
export type WorkspaceMirrorRow = {
  id: string;
  host: HostRef | null;
  kind: 'repository' | 'worktree' | 'directory' | null;
  path: string | null;
  parentId: string | null;
  origin: 'registered' | 'adopted' | null;
  /** Client-owned rich-provenance annotation; adopted rows have none. */
  config: WorkspaceConfig | null;
  observedStatus: 'present' | 'missing' | null;
  observedGit: WorkspaceObservedGit | null;
  lastCreateOutcome: WorkspaceCreateOutcome | null;
  /** Last failed removal attempt (ADR 0006); host-written, null while none failed. */
  lastRemovalAttempt: WorkspaceRemovalAttempt | null;
  /** Durable per-script (prepare/setup/run) last outcomes; survive daemon restarts. */
  scriptOutcomes: WorkspaceScriptOutcomes | null;
  runtimeOverlay: WorkspaceRuntimeOverlay | null;
  /** Epoch-ms; observation only, never a durable "active" flag. */
  lastActivatedAt: number | null;
  /** Epoch-ms host observation stamp; staleness is displayed, not hidden. */
  observedAt: number | null;
  createdAt: string;
  updatedAt: string;
  /** Set for desktop-untracked rows (tombstones); served when includeUntracked. */
  untrackedAt: string | null;
};
