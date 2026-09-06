import { describe, expect, it } from 'vitest';
import {
  GIT_CREDENTIAL_HELPER_COMMAND,
  type GitCredentialsSessionSpec,
} from '#primitives/git-credentials/api';
import { buildTerminalEnv } from './terminal-env';

// Stand-in for a real provider token held desktop-side. It must never appear
// anywhere in a session environment, in any credentials mode.
const SECRET_TOKEN = 'ghp_SECRET_TOKEN_MATERIAL_do_not_leak';

const channel = { port: 51234, nonce: 'session-nonce' };

const MODES: Record<string, GitCredentialsSessionSpec | undefined> = {
  'effective-account': { mode: 'effective-account', channel, hosts: ['github.com'] },
  system: { mode: 'system' },
  none: { mode: 'none' },
  absent: undefined,
};

describe('buildTerminalEnv git credentials', () => {
  it.each(Object.entries(MODES))('mode %s contains no token material', (_name, spec) => {
    const env = buildTerminalEnv({
      baseEnv: { PATH: '/bin', HOME: '/home/u' },
      ...(spec ? { gitCredentials: spec } : {}),
    });
    expect(JSON.stringify(env)).not.toContain(SECRET_TOKEN);
    for (const value of Object.values(env)) {
      expect(value).not.toMatch(/gh[pousr]_[A-Za-z0-9]/);
    }
  });

  it('effective-account wires the helper config and channel env', () => {
    const env = buildTerminalEnv({
      baseEnv: { PATH: '/bin' },
      gitCredentials: MODES['effective-account'],
    });
    expect(env.EMDASH_GIT_CREDENTIAL_PORT).toBe('51234');
    expect(env.EMDASH_GIT_CREDENTIAL_NONCE).toBe('session-nonce');
    expect(env.GIT_CONFIG_COUNT).toBe('2');
    expect(env.GIT_CONFIG_KEY_0).toBe('credential.https://github.com.helper');
    expect(env.GIT_CONFIG_VALUE_0).toBe('');
    expect(env.GIT_CONFIG_VALUE_1).toBe(GIT_CREDENTIAL_HELPER_COMMAND);
  });

  it('none scrubs credential helpers even when overrides set them', () => {
    const env = buildTerminalEnv({
      baseEnv: { PATH: '/bin', GIT_ASKPASS: '/usr/local/bin/gh-askpass' },
      overrides: { GIT_ASKPASS: '/usr/local/bin/other-askpass' },
      gitCredentials: MODES.none,
    });
    expect(env.GIT_ASKPASS).toBe('');
    expect(env.SSH_ASKPASS).toBe('');
    expect(env.GIT_CONFIG_COUNT).toBe('1');
    expect(env.GIT_CONFIG_KEY_0).toBe('credential.helper');
    expect(env.GIT_CONFIG_VALUE_0).toBe('');
  });

  it('system and absent leave credential-related env untouched', () => {
    for (const spec of [MODES.system, MODES.absent]) {
      const env = buildTerminalEnv({
        baseEnv: { PATH: '/bin', GIT_ASKPASS: '/usr/local/bin/gh-askpass' },
        ...(spec ? { gitCredentials: spec } : {}),
      });
      expect(env.GIT_ASKPASS).toBe('/usr/local/bin/gh-askpass');
      expect(env.GIT_CONFIG_COUNT).toBeUndefined();
      expect(env.EMDASH_GIT_CREDENTIAL_PORT).toBeUndefined();
    }
  });
});
