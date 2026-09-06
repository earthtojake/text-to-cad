import { z } from 'zod';

/**
 * Session-env construction for the emdash git credential helper
 * (spec: github-git-settings §4, invariants 4 and 5).
 *
 * Raw tokens never enter a session environment. Sessions carry only a
 * per-session channel — the loopback port and a random nonce — and a
 * `credential.<url>.helper` git config (via `GIT_CONFIG_*` env) whose helper
 * command forwards git's credential request to the desktop over that channel.
 * The desktop re-resolves the effective account and returns the credential on
 * the helper's stdout; nothing token-shaped ever lands in env, argv, or logs.
 */

export const gitCredentialChannelSchema = z.object({
  /** Loopback port of the desktop credential server. */
  port: z.number().int().min(1).max(65535),
  /** Per-session channel auth nonce — never a provider token. */
  nonce: z.string().min(1),
});

export type GitCredentialChannel = z.infer<typeof gitCredentialChannelSchema>;

/**
 * The per-session credentials behavior, resolved desktop-side from the
 * per-project "agent git credentials" setting and the effective account:
 *
 * - `effective-account`: wire the emdash helper for the given hosts; other
 *   hosts keep native behavior.
 * - `system`: leave the environment untouched (native credential behavior).
 * - `none`: actively scrub credential helpers from the session env
 *   (GIT_ASKPASS/SSH_ASKPASS and `credential.helper` overrides).
 */
export const gitCredentialsSessionSpecSchema = z.discriminatedUnion('mode', [
  z.object({
    mode: z.literal('effective-account'),
    channel: gitCredentialChannelSchema,
    /** Normalized HTTPS hosts the helper answers for (e.g. "github.com"). */
    hosts: z.array(z.string().min(1)).min(1),
  }),
  z.object({ mode: z.literal('system') }),
  z.object({ mode: z.literal('none') }),
]);

export type GitCredentialsSessionSpec = z.infer<typeof gitCredentialsSessionSpecSchema>;

export const GIT_CREDENTIAL_PORT_ENV_VAR = 'EMDASH_GIT_CREDENTIAL_PORT';
export const GIT_CREDENTIAL_NONCE_ENV_VAR = 'EMDASH_GIT_CREDENTIAL_NONCE';
export const GIT_CREDENTIAL_HELPER_URL_PATH = '/git-credential/get';

/**
 * The credential helper as a git `!shell` helper command (same transport shape
 * as the TUI hook commands: curl to a loopback port with a nonce header). The
 * port and nonce are read from the session env at invocation time so neither
 * appears in git config values or process argv. Only the `get` action is
 * answered; `store`/`erase` are no-ops. Failures print nothing, so git falls
 * through to its normal prompting behavior.
 */
export const GIT_CREDENTIAL_HELPER_COMMAND =
  '!f() { if [ "$1" = get ]; then ' +
  'curl -s -f -m 10 -X POST --data-binary @- ' +
  `-H "X-Emdash-Token: $${GIT_CREDENTIAL_NONCE_ENV_VAR}" ` +
  `"http://127.0.0.1:$${GIT_CREDENTIAL_PORT_ENV_VAR}${GIT_CREDENTIAL_HELPER_URL_PATH}" ` +
  '2>/dev/null || true; fi; }; f';

const CREDENTIAL_HELPER_CONFIG_KEY = /^credential(\..+)?\.helper$/i;

type GitConfigPair = { key: string; value: string };

/**
 * Applies a git-credentials session spec to a fully-composed session env.
 * This is the single blessed construction point for git-credential env; PTY
 * runtimes must route through it (directly or via `buildTerminalEnv`) instead
 * of assembling `GIT_CONFIG_*`/askpass entries themselves.
 */
export function applyGitCredentialsToEnv(
  env: Record<string, string>,
  spec: GitCredentialsSessionSpec | undefined
): Record<string, string> {
  if (!spec || spec.mode === 'system') return env;
  return spec.mode === 'none' ? scrubCredentialHelpers(env) : injectEmdashHelper(env, spec);
}

/**
 * Per-operation env for emdash's own git invocations: the helper scoped to a
 * single host over an operation-scoped channel, overlaid onto the git
 * runtime's process env for that one command.
 */
export function gitCredentialOperationEnv(
  channel: GitCredentialChannel,
  host: string
): Record<string, string> {
  return applyGitCredentialsToEnv({}, { mode: 'effective-account', channel, hosts: [host] });
}

function injectEmdashHelper(
  env: Record<string, string>,
  spec: Extract<GitCredentialsSessionSpec, { mode: 'effective-account' }>
): Record<string, string> {
  const pairs = readGitConfigPairs(env);
  for (const host of spec.hosts) {
    const key = `credential.https://${host}.helper`;
    // An empty entry resets previously-configured helpers for this host so
    // the session authenticates as exactly the effective account there;
    // other hosts keep native behavior.
    pairs.push({ key, value: '' });
    pairs.push({ key, value: GIT_CREDENTIAL_HELPER_COMMAND });
  }
  return {
    ...withoutGitConfigEntries(env),
    [GIT_CREDENTIAL_PORT_ENV_VAR]: String(spec.channel.port),
    [GIT_CREDENTIAL_NONCE_ENV_VAR]: spec.channel.nonce,
    ...gitConfigEnv(pairs),
  };
}

function scrubCredentialHelpers(env: Record<string, string>): Record<string, string> {
  const pairs = readGitConfigPairs(env).filter(
    (pair) => !CREDENTIAL_HELPER_CONFIG_KEY.test(pair.key)
  );
  // A single empty credential.helper entry resets every helper configured in
  // system/global/local git config (the decision ticket's scrub semantics).
  pairs.push({ key: 'credential.helper', value: '' });

  const scrubbed = withoutGitConfigEntries(env);
  delete scrubbed[GIT_CREDENTIAL_PORT_ENV_VAR];
  delete scrubbed[GIT_CREDENTIAL_NONCE_ENV_VAR];
  return {
    ...scrubbed,
    // Empty (not unset): git treats an empty askpass as "no askpass", and an
    // env-level empty wins over core.askpass config.
    GIT_ASKPASS: '',
    SSH_ASKPASS: '',
    ...gitConfigEnv(pairs),
  };
}

function readGitConfigPairs(env: Record<string, string>): GitConfigPair[] {
  const count = Number.parseInt(env.GIT_CONFIG_COUNT ?? '', 10);
  if (!Number.isInteger(count) || count <= 0) return [];
  const pairs: GitConfigPair[] = [];
  for (let index = 0; index < count; index += 1) {
    const key = env[`GIT_CONFIG_KEY_${index}`];
    const value = env[`GIT_CONFIG_VALUE_${index}`];
    if (key === undefined || value === undefined) continue;
    pairs.push({ key, value });
  }
  return pairs;
}

function withoutGitConfigEntries(env: Record<string, string>): Record<string, string> {
  const next: Record<string, string> = {};
  for (const [key, value] of Object.entries(env)) {
    if (key === 'GIT_CONFIG_COUNT' || /^GIT_CONFIG_(KEY|VALUE)_\d+$/.test(key)) continue;
    next[key] = value;
  }
  return next;
}

function gitConfigEnv(pairs: GitConfigPair[]): Record<string, string> {
  const env: Record<string, string> = { GIT_CONFIG_COUNT: String(pairs.length) };
  pairs.forEach((pair, index) => {
    env[`GIT_CONFIG_KEY_${index}`] = pair.key;
    env[`GIT_CONFIG_VALUE_${index}`] = pair.value;
  });
  return env;
}
