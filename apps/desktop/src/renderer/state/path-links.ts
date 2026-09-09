import { create } from "zustand";

import type { PathKind } from "@shared/ipc/explorer";
import type { ExplorerRoot } from "@shared/types";

/**
 * Which of the paths an agent has written actually exist (plan §8: a
 * workspace-relative path in a message becomes a link — when it is one).
 *
 * The transcript's markdown renderer marks every path-shaped token as a
 * link candidate without knowing whether there is such a file; each
 * candidate's component asks here. Asking main per token would be one IPC
 * round trip per word of a file listing, so the questions are batched: the
 * first `lookup` in a tick schedules a microtask, everything asked before
 * it runs goes into one `explorer.exists` per root, and the answers land
 * in the cache together. A path is marked `pending` the moment it is
 * queued, so a message rendering the same path five times asks once.
 *
 * The cache is per (project, root) and is cleared for a root's changed
 * paths on every `files.changed` batch (`state/bridge.ts`): a file the
 * agent is about to write shows as text until it exists, then as a link.
 */
export type PathAnswer = PathKind | "pending";

type Scope = { projectId: string; root: ExplorerRoot };

type PathLinksState = {
  /** `scopeKey(scope)` -> path -> what is there. */
  kinds: Record<string, Record<string, PathAnswer>>;
  /** Ask, if the answer is not already here or on its way. */
  lookup: (scope: Scope, paths: readonly string[]) => void;
  /** Forget the answers for these paths (or all of the root's, when omitted). */
  invalidate: (scope: Scope, paths?: readonly string[]) => void;
  /** The batch, sent. Exported for the tests; called from a microtask otherwise. */
  flush: () => Promise<void>;
};

export function scopeKey(scope: Scope): string {
  return `${scope.projectId}::${scope.root ?? ""}`;
}

/** The questions not yet sent, per scope. */
const queued = new Map<string, { scope: Scope; paths: Set<string> }>();
let scheduled = false;

export const usePathLinks = create<PathLinksState>((set, get) => ({
  kinds: {},

  lookup: (scope, paths) => {
    const key = scopeKey(scope);
    const known = get().kinds[key] ?? {};
    const fresh = paths.filter((path) => known[path] === undefined);
    if (fresh.length === 0) {
      return;
    }
    set((state) => ({
      kinds: {
        ...state.kinds,
        [key]: { ...(state.kinds[key] ?? {}), ...Object.fromEntries(fresh.map((path) => [path, "pending" as const])) },
      },
    }));
    let batch = queued.get(key);
    if (!batch) {
      batch = { scope, paths: new Set() };
      queued.set(key, batch);
    }
    for (const path of fresh) {
      batch.paths.add(path);
    }
    if (!scheduled) {
      scheduled = true;
      queueMicrotask(() => void get().flush());
    }
  },

  invalidate: (scope, paths) => {
    const key = scopeKey(scope);
    set((state) => {
      const current = state.kinds[key];
      if (!current) {
        return state;
      }
      if (!paths) {
        const { [key]: _dropped, ...rest } = state.kinds;
        return { kinds: rest };
      }
      const next = { ...current };
      for (const path of paths) {
        delete next[path];
      }
      return { kinds: { ...state.kinds, [key]: next } };
    });
  },

  flush: async () => {
    scheduled = false;
    const batches = [...queued.values()];
    queued.clear();
    await Promise.all(
      batches.map(async ({ scope, paths }) => {
        const key = scopeKey(scope);
        const asked = [...paths];
        let answers: Record<string, PathKind>;
        try {
          answers = await window.hardcore.explorer.exists({
            projectId: scope.projectId,
            ...(scope.root ? { root: scope.root } : {}),
            paths: asked,
          });
        } catch {
          // A project that is gone, or a root that is: nothing there links.
          answers = Object.fromEntries(asked.map((path) => [path, null]));
        }
        set((state) => ({
          kinds: {
            ...state.kinds,
            [key]: {
              ...(state.kinds[key] ?? {}),
              ...Object.fromEntries(asked.map((path) => [path, answers[path] ?? null])),
            },
          },
        }));
      }),
    );
  },
}));

/** One path's answer in a scope, or undefined when nobody has asked yet. */
export function usePathKind(scope: Scope | null, path: string): PathAnswer | undefined {
  return usePathLinks((state) => (scope ? state.kinds[scopeKey(scope)]?.[path] : undefined));
}
