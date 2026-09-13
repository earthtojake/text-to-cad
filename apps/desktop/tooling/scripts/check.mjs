/**
 * Root merge gate: runs format, lint, typecheck, and test in order via the
 * existing Nx-powered root scripts. Equivalent to running the four commands
 * by hand; stops at the first failure.
 */
import { spawnSync } from 'node:child_process';

const steps = ['format', 'lint', 'typecheck', 'test'];

for (const step of steps) {
  console.log(`\ncheck: running pnpm run ${step}\n`);
  const result = spawnSync('pnpm', ['run', step], {
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
  if (result.status !== 0) {
    console.error(
      `\ncheck: failed at "pnpm run ${step}".` +
        '\nIf the failure looks environmental, run `pnpm run doctor` to rule out your setup.'
    );
    process.exit(typeof result.status === 'number' ? result.status : 1);
  }
}

console.log('\ncheck: format, lint, typecheck, and test all passed.');
