/**
 * Filesystem and pty services behind the explorer strip. **Filled by P3.**
 *
 * `fs.ts` (tree, read, write, chokidar watch) and `terminal.ts` (node-pty).
 * ACP's `fs/*` and `terminal/*` requests are routed through these same
 * services, so an agent's write refreshes an open editor instead of racing it.
 */
export {};
