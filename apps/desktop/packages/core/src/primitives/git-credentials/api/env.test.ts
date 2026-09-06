import { describe, expect, it } from 'vitest';
import {
  applyGitCredentialsToEnv,
  GIT_CREDENTIAL_HELPER_COMMAND,
  gitCredentialOperationEnv,
  type GitCredentialsSessionSpec,
} from './env';

const channel = { port: 45678, nonce: 'channel-nonce-1234' };

const helperSpec: GitCredentialsSessionSpec = {
  mode: 'effective-account',
  channel,
  hosts: ['github.com'],
};

function gitConfigPairs(env: Record<string, string>): [string, string][] {
  const count = Number(env.GIT_CONFIG_COUNT ?? '0');
  const pairs: [string, string][] = [];
  for (let i = 0; i < count; i += 1) {
    pairs.push([env[`GIT_CONFIG_KEY_${i}`]!, env[`GIT_CONFIG_VALUE_${i}`]!]);
  }
  return pairs;
}

describe('applyGitCredentialsToEnv', () => {
  it('returns the env untouched for system mode and for no spec', () => {
    const env = { PATH: '/bin', GIT_ASKPASS: '/usr/bin/whatever' };
    expect(applyGitCredentialsToEnv(env, { mode: 'system' })).toEqual(env);
    expect(applyGitCredentialsToEnv(env, undefined)).toEqual(env);
  });

  describe('effective-account mode', () => {
    it('wires the helper for each host with a reset entry first', () => {
      const env = applyGitCredentialsToEnv({ PATH: '/bin' }, helperSpec);
      expect(env.EMDASH_GIT_CREDENTIAL_PORT).toBe('45678');
      expect(env.EMDASH_GIT_CREDENTIAL_NONCE).toBe('channel-nonce-1234');
      expect(gitConfigPairs(env)).toEqual([
        ['credential.https://github.com.helper', ''],
        ['credential.https://github.com.helper', GIT_CREDENTIAL_HELPER_COMMAND],
      ]);
    });

    it('appends after pre-existing GIT_CONFIG entries instead of clobbering them', () => {
      const env = applyGitCredentialsToEnv(
        {
          GIT_CONFIG_COUNT: '1',
          GIT_CONFIG_KEY_0: 'user.name',
          GIT_CONFIG_VALUE_0: 'Someone',
        },
        helperSpec
      );
      expect(gitConfigPairs(env)).toEqual([
        ['user.name', 'Someone'],
        ['credential.https://github.com.helper', ''],
        ['credential.https://github.com.helper', GIT_CREDENTIAL_HELPER_COMMAND],
      ]);
    });

    it('references the channel through env vars, never inline in config values', () => {
      const env = applyGitCredentialsToEnv({}, helperSpec);
      for (const [, value] of gitConfigPairs(env)) {
        expect(value).not.toContain(channel.nonce);
        expect(value).not.toContain(String(channel.port));
      }
    });

    it('does not touch askpass behavior', () => {
      const env = applyGitCredentialsToEnv({ GIT_ASKPASS: '/usr/bin/x' }, helperSpec);
      expect(env.GIT_ASKPASS).toBe('/usr/bin/x');
    });
  });

  describe('none mode', () => {
    it('scrubs askpass and resets credential helpers', () => {
      const env = applyGitCredentialsToEnv(
        { PATH: '/bin', GIT_ASKPASS: '/usr/bin/x', SSH_ASKPASS: '/usr/bin/y' },
        { mode: 'none' }
      );
      expect(env.GIT_ASKPASS).toBe('');
      expect(env.SSH_ASKPASS).toBe('');
      expect(gitConfigPairs(env)).toEqual([['credential.helper', '']]);
    });

    it('drops credential.helper overrides from pre-existing GIT_CONFIG entries', () => {
      const env = applyGitCredentialsToEnv(
        {
          GIT_CONFIG_COUNT: '3',
          GIT_CONFIG_KEY_0: 'credential.helper',
          GIT_CONFIG_VALUE_0: '!leaky',
          GIT_CONFIG_KEY_1: 'user.name',
          GIT_CONFIG_VALUE_1: 'Someone',
          GIT_CONFIG_KEY_2: 'credential.https://github.com.helper',
          GIT_CONFIG_VALUE_2: '!leaky-too',
        },
        { mode: 'none' }
      );
      expect(gitConfigPairs(env)).toEqual([
        ['user.name', 'Someone'],
        ['credential.helper', ''],
      ]);
    });

    it('removes an emdash helper channel if one is present', () => {
      const helperEnv = applyGitCredentialsToEnv({ PATH: '/bin' }, helperSpec);
      const scrubbed = applyGitCredentialsToEnv(helperEnv, { mode: 'none' });
      expect(scrubbed.EMDASH_GIT_CREDENTIAL_PORT).toBeUndefined();
      expect(scrubbed.EMDASH_GIT_CREDENTIAL_NONCE).toBeUndefined();
      expect(gitConfigPairs(scrubbed)).toEqual([['credential.helper', '']]);
    });
  });
});

describe('gitCredentialOperationEnv', () => {
  it('produces a standalone overlay for one host', () => {
    const env = gitCredentialOperationEnv(channel, 'github.example.com');
    expect(env.EMDASH_GIT_CREDENTIAL_PORT).toBe('45678');
    expect(gitConfigPairs(env)).toEqual([
      ['credential.https://github.example.com.helper', ''],
      ['credential.https://github.example.com.helper', GIT_CREDENTIAL_HELPER_COMMAND],
    ]);
  });
});
