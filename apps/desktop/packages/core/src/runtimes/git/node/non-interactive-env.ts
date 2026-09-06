export const NON_INTERACTIVE_GIT_ENV = {
  GIT_ASKPASS: '',
  GIT_TERMINAL_PROMPT: '0',
  GCM_INTERACTIVE: 'never',
  SSH_ASKPASS: '',
} as const;

/**
 * Environment for the git runtime worker and the git subprocesses it spawns:
 * never prompt for credentials (the worker has no terminal to answer on), and
 * force the C locale so parsed git output is stable across user locales.
 */
export function gitRuntimeEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return {
    ...env,
    ...NON_INTERACTIVE_GIT_ENV,
    LC_ALL: 'C',
    LANG: 'C',
    LANGUAGE: 'C',
  };
}
