/**
 * Project services. The sqlite side is `src/main/db/repositories.ts`; this is
 * where watching and git go.
 *
 * `git.ts` carries what the review tab reads — status, the two sides of a
 * file, the unified patch — and its `Commit or push`. **P7 fills in the rest**
 * (plan §9): the three git modes, worktree creation and deletion, and
 * `Create pull request` via `gh`.
 *
 * Watching lives in `src/main/explorer/fs.ts`, next to the tree it feeds,
 * rather than in a `watcher.ts` here: there is one watcher per project root
 * and its only consumer is the explorer.
 */
export * from "./git";
