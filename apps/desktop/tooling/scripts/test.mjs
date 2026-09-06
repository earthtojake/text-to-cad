/**
 * Root test runner: delegates to the Nx-powered test targets across the
 * workspace and, on failure, points at the doctor — mirroring the referral
 * that tooling/scripts/check.mjs prints for the full merge gate.
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const DOCTOR_HINT =
  'If the failure looks environmental, run `pnpm run doctor` to rule out your setup.';

/**
 * Runs the workspace test targets; returns the exit code to use.
 * `spawn` and `log` are injectable for tests (see
 * apps/emdash-desktop/scripts/root-test-wrapper.test.ts).
 */
export function runRootTests({ argv = [], spawn = spawnSync, log = console.error } = {}) {
  const result = spawn('pnpm', ['exec', 'nx', 'run-many', '-t', 'test', '--all', ...argv], {
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
  if (result.status === 0) {
    return 0;
  }
  log(`\ntest: failed.\n${DOCTOR_HINT}`);
  return typeof result.status === 'number' ? result.status : 1;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(runRootTests({ argv: process.argv.slice(2) }));
}
