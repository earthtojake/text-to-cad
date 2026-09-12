/**
 * The filesystem and pty services behind the explorer strip.
 *
 * `fs.ts` is the tree, the ignore rules, the reads and writes, and one
 * chokidar watcher per project root; `terminal.ts` is the node-pty sessions
 * and the scrollback that lets a reattaching tab replay what it missed.
 *
 * Both are plain Node — no Electron import — so they can be unit-tested
 * (`tests/unit/main/explorer-fs.test.ts`). The Electron half is
 * `src/main/ipc/explorer.ts`, which turns a `projectId` into a root and
 * refuses every path that lands outside it.
 *
 * P1's ACP client routes `fs/*` and `terminal/*` through these same services,
 * so an agent's write refreshes an open editor instead of racing it.
 */
export * from "./fs";
export * from "./terminal";
