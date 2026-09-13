import type { EnvSource } from '#primitives/exec/api';
import { createBoundExec, type BoundExec, type ExecOptions } from '#services/exec/api';
import {
  GitSchedule,
  WorktreeWriteLocks,
  type GitScheduleOptions,
  type GitWorkTier,
} from './git-schedule';

export type RegistryGitExecOptions = {
  /** Budget priority class; defaults to 'probe' (the safe floor for read paths). */
  tier?: GitWorkTier;
  /** Repository key for idle gating; only meaningful for tiers above 'probe'. */
  repository?: string;
};

export type CreateRegistryGitContextOptions = GitScheduleOptions & {
  env?: EnvSource;
};

/**
 * The runtime-owned git dependency bundle (spec: registry-runtime-carveout): the
 * subprocess budget, the per-worktree writer locks, and the budgeted exec factory,
 * injected into the executors and the scan plane instead of imported as process
 * globals. One context per runtime — two runtimes in one process never share gates.
 */
export type RegistryGitContext = {
  schedule: GitSchedule;
  locks: WorktreeWriteLocks;
  /** The budgeted git exec factory — {@link createRegistryGitExec} bound to `schedule`. */
  exec(cwd: string, options?: RegistryGitExecOptions): BoundExec;
};

/** Builds a real context; `GitScheduleOptions` is the composition-test lever. */
export function createRegistryGitContext(
  options: CreateRegistryGitContextOptions = {}
): RegistryGitContext {
  const schedule = new GitSchedule(options);
  const env = options.env ?? (async () => process.env);
  return {
    schedule,
    locks: new WorktreeWriteLocks(),
    exec: (cwd, execOptions) => createRegistryGitExec(schedule, env, cwd, execOptions),
  };
}

/**
 * Every registry git subprocess flows through the context's budget (spec: git
 * concurrency model) — buffered exec calls acquire a slot for the subprocess's
 * lifetime at the caller's tier. Spawn-based callers gate through `schedule.run`
 * themselves because they retain the child process after creation.
 */
function createRegistryGitExec(
  schedule: GitSchedule,
  env: EnvSource,
  cwd: string,
  options: RegistryGitExecOptions = {}
): BoundExec {
  const tier = options.tier ?? 'probe';
  const work = { tier, repository: options.repository };
  const inner = createBoundExec({
    file: 'git',
    cwd,
    env: async () => registryGitEnv(await env(), tier === 'probe'),
  });
  return {
    get file() {
      return inner.file;
    },
    get cwd() {
      return inner.cwd;
    },
    get env() {
      return inner.env;
    },
    exec: (args: string[], execOptions?: ExecOptions) =>
      schedule.run(work, () => inner.exec(args, execOptions)),
    execStreaming: (args, onStdout, execOptions) =>
      schedule.run(work, () => inner.execStreaming(args, onStdout, execOptions)),
    execBuffer: (args, execOptions) =>
      schedule.run(work, () => inner.execBuffer(args, execOptions)),
    spawn: (args, spawnOptions) => inner.spawn(args, spawnOptions),
    withCwd: (nextCwd: string) => createRegistryGitExec(schedule, env, nextCwd, options),
  };
}

function registryGitEnv(base: NodeJS.ProcessEnv, probe: boolean): NodeJS.ProcessEnv {
  return {
    ...base,
    LC_ALL: 'C',
    LANG: 'C',
    LANGUAGE: 'C',
    GIT_TERMINAL_PROMPT: '0',
    GIT_ASKPASS: '',
    ...(probe ? { GIT_OPTIONAL_LOCKS: '0' } : {}),
  };
}
