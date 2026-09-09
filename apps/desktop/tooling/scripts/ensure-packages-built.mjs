/**
 * Builds the workspace packages before a flow that bypasses Nx task
 * orchestration — app-only dev (`pnpm run dev` from apps/emdash-desktop) and
 * Storybook run their underlying tool directly, so on a never-built clone the
 * workspace `dist/` outputs their imports resolve to would not exist yet.
 *
 * When the calling script is itself executed as an Nx task (root `pnpm run
 * dev`, `nx storybook @emdash/ui`, ...), Nx's `^build` dependency wiring has
 * already ordered the builds, so this exits immediately. Warm re-runs are Nx
 * cache hits and cost around a second.
 */
import { spawnSync } from 'node:child_process';

if (process.env.NX_TASK_TARGET_PROJECT) {
  process.exit(0);
}

const result = spawnSync(
  'pnpm',
  [
    'exec',
    'nx',
    'run-many',
    '-t',
    'build',
    '--exclude',
    '@hardcore/desktop,@emdash/workspace-server',
  ],
  { stdio: 'inherit', shell: process.platform === 'win32' }
);
process.exit(typeof result.status === 'number' ? result.status : 1);
