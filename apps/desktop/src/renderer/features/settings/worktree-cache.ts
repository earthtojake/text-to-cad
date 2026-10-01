/**
 * The Git page's worktree lists, kept for the Settings visit.
 *
 * Searching mounts every page and clearing the query unmounts all but the open
 * one, so type, clear, type would read every project's worktrees (a `git
 * worktree list` plus three git calls per worktree for its date) each time the
 * Git page came back. The lists live here instead, and go when Settings closes.
 *
 * A card that mounts reads afresh over the kept list (`ensureWorktrees` with
 * `fresh`): a file removed on disk makes a worktree clean, and coming back to
 * the page has to show it. Between mounts only an invalidation reads again: a
 * worktree deleted from the page, or a `sessions.changed` that changed the
 * usage string (`usageOf`: each session's id, cwd, worktreePath and archived
 * flag, which is all a row's "in use" depends on). Status, title and diff
 * counts change with every turn and invalidate nothing. The list stays on the
 * page, marked old, until the fresh read replaces it: a card that vanished and
 * came back on every broadcast would flicker, and each broadcast would cost a
 * `git worktree list` plus three git calls per worktree.
 */
import { create } from "zustand";

import type { Worktree } from "@shared/ipc/git";
import type { Session } from "@shared/types";

type WorktreeCache = {
  lists: Record<string, Worktree[]>;
  /** The epoch each list was read at; a list from an older epoch is shown, and read again. */
  readAt: Record<string, number>;
  /** Bumped by every invalidation: the cards mounted at the time read again. */
  epoch: number;
  /** Mark every list old; they stay visible until their re-read lands. */
  invalidate: () => void;
  /** Forget every list: Settings closed. */
  clear: () => void;
};

export const useWorktreeCache = create<WorktreeCache>((set) => ({
  lists: {},
  readAt: {},
  epoch: 0,
  invalidate: () => set((state) => ({ epoch: state.epoch + 1 })),
  clear: () => set((state) => ({ lists: {}, readAt: {}, epoch: state.epoch + 1 })),
}));

/** Reads under way, one per project and epoch: a read begun before an invalidation is not the answer to the next. */
const inflight = new Map<string, Promise<void>>();

/**
 * Read a project's worktrees. A card that mounts reads afresh (`fresh`): a file
 * the person removed on disk makes a worktree clean, and coming back to the
 * page has to show that. Between mounts only an invalidation reads again, and a
 * read under way is shared. The old list stays on the page until the new one
 * lands. A failed read is not kept.
 */
export function ensureWorktrees(projectId: string, { fresh = false } = {}): Promise<void> {
  const { epoch, readAt } = useWorktreeCache.getState();
  if (!fresh && readAt[projectId] === epoch) {
    return Promise.resolve();
  }
  const key = `${projectId}:${epoch}`;
  const running = inflight.get(key);
  if (running) {
    return running;
  }
  const read = window.textToCad.git
    .worktrees({ projectId })
    .then((list) => {
      // An invalidation since the read began means the answer is already old,
      // and the card's effect has started the read that replaces it.
      if (useWorktreeCache.getState().epoch === epoch) {
        useWorktreeCache.setState((state) => ({
          lists: { ...state.lists, [projectId]: list },
          readAt: { ...state.readAt, [projectId]: epoch },
        }));
      }
    })
    .catch(() => {})
    .finally(() => inflight.delete(key));
  inflight.set(key, read);
  return read;
}

/**
 * What a worktree row depends on in the session list: which sessions there are,
 * where each runs, and whether it is archived (`sessionsUsing`). Status, title
 * and diff counts change with every turn and say nothing about a row.
 */
function usageOf(sessions: readonly Session[]): string {
  return sessions
    .map((session) => `${session.id}\0${session.cwd}\0${session.worktreePath ?? ""}\0${session.archived}`)
    .sort()
    .join("\n");
}

let usage: string | null = null;

/** Note the session list Settings opened with, so the first broadcast has something to differ from. */
export function seedSessions(sessions: readonly Session[]): void {
  usage = usageOf(sessions);
}

/** A `sessions.changed`: mark the lists old only when it changed what a row says. */
export function noteSessions(sessions: readonly Session[]): void {
  const next = usageOf(sessions);
  if (next !== usage) {
    usage = next;
    useWorktreeCache.getState().invalidate();
  }
}

/** Forget every read and the remembered session usage: the module's state outlives a test's store reset. */
export function resetForTests(): void {
  inflight.clear();
  usage = null;
  useWorktreeCache.setState({ lists: {}, readAt: {}, epoch: 0 });
}
