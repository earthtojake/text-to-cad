import type { WorktreeRootContext } from './worktree-root';

/**
 * Host- and app-owned placement layers below per-project overrides. The node
 * settings provider supplies this context unchanged to both execution and the
 * renderer so every consumer resolves the same effective values.
 */
export type PlacementContext = WorktreeRootContext & {
  /** Per-host tmux default; null means the host has no override. */
  hostTmux: boolean | null;
  /** Desktop-wide fallback used when the host has no tmux default. */
  appDefaultTmux: boolean;
};
