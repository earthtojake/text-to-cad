import os from 'node:os';
import {
  applyGitCredentialsToEnv,
  type GitCredentialsSessionSpec,
} from '#primitives/git-credentials/api';
import type { ResolvedPtyShellProfile } from './local-spawn';

export function buildTerminalEnv(options: {
  shellProfile?: ResolvedPtyShellProfile;
  baseEnv: NodeJS.ProcessEnv | Record<string, string | undefined>;
  overrides?: Record<string, string | undefined>;
  /**
   * Per-session git credential behavior (spec: github-git-settings §4).
   * Applied last so scrubbing ("none") wins over base env and overrides;
   * absent means native/system behavior.
   */
  gitCredentials?: GitCredentialsSessionSpec;
}): Record<string, string> {
  const source = options.baseEnv;
  const env: Record<string, string> = {};
  for (const [key, val] of Object.entries(source)) {
    if (val !== undefined) env[key] = val;
  }

  env.TERM = 'xterm-256color';
  env.COLORTERM = 'truecolor';
  env.TERM_PROGRAM = 'emdash';

  if (process.platform !== 'win32') {
    env.SHELL =
      options.shellProfile?.family === 'posix' || options.shellProfile?.family === 'csh'
        ? options.shellProfile.executable
        : (env.SHELL ?? (process.platform === 'darwin' ? '/bin/zsh' : '/bin/bash'));
  } else if (source.SHELL) {
    env.SHELL = source.SHELL;
  }

  env.HOME ??= os.homedir();

  for (const [key, val] of Object.entries(options.overrides ?? {})) {
    if (val === undefined) delete env[key];
    else env[key] = val;
  }

  return applyGitCredentialsToEnv(env, options.gitCredentials);
}
