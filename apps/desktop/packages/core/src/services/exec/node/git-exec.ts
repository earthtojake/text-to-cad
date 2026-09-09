import { createBoundExec, type BoundExec } from '#services/exec/api';

export type GitExecFactory = (cwd: string) => BoundExec;

/**
 * Non-interactive git exec bound to `cwd`. Git needs the full process env (PATH, HOME,
 * SSH_AUTH_SOCK, credential helpers), so it is composed in here — exec itself never
 * merges `process.env`. Every prompt channel is disabled so background git work fails
 * fast instead of blocking on credential or host-key input.
 */
export function createNonInteractiveGitExec(cwd: string): BoundExec {
  return createBoundExec({
    file: 'git',
    cwd,
    env: {
      ...process.env,
      LC_ALL: 'C',
      LANG: 'C',
      LANGUAGE: 'C',
      GIT_TERMINAL_PROMPT: '0',
      GCM_INTERACTIVE: 'never',
      GIT_ASKPASS: '',
      SSH_ASKPASS: '',
      ...(process.env.GIT_SSH_COMMAND ? {} : { GIT_SSH_COMMAND: 'ssh -o BatchMode=yes' }),
    },
  });
}

export const defaultGitExecFactory: GitExecFactory = (cwd) => createNonInteractiveGitExec(cwd);
