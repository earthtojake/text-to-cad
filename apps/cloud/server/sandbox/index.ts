import type { Config } from '../config.ts';
import { createLocalSandbox } from './local.ts';
import type { SandboxProvider } from './protocol.ts';
import { createVercelSandbox } from './vercel.ts';

export * from './protocol.ts';

export function createSandbox(config: Config): SandboxProvider {
  const sandbox = config.sandbox;
  if (sandbox.kind === 'vercel') {
    return createVercelSandbox({
      snapshotId: sandbox.snapshotId,
      python: sandbox.python,
      runner: sandbox.runner,
      jobRoot: sandbox.jobRoot,
      credentials: sandbox.credentials,
    });
  }
  return createLocalSandbox({
    python: sandbox.python,
    runner: sandbox.runner,
    jobsDir: sandbox.jobsDir,
    production: config.production,
    allowInProduction: sandbox.allowInProduction,
    keepJobs: process.env.CLOUD_KEEP_JOBS === '1',
  });
}
