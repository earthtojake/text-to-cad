import { describe, expect, it } from 'vitest';
import { buildUserShellEnvSeed } from './user-env';

describe('buildUserShellEnvSeed', () => {
  it('keeps user/session values and removes host runtime controls', () => {
    expect(
      buildUserShellEnvSeed({
        HOME: '/home/test',
        PATH: '/usr/bin',
        SSH_AUTH_SOCK: '/tmp/agent.sock',
        CUSTOM_USER_VALUE: 'kept',
        NODE_ENV: 'production',
        NODE_ENV_ELECTRON_VITE: 'development',
        ELECTRON_RUN_AS_NODE: '1',
        ELECTRON_EXEC_PATH: '/app/node_modules/electron',
        EMDASH_DB_FILE: '/tmp/app.db',
        EMDASH_LOG_FILE: '/tmp/app.log',
        npm_lifecycle_event: 'dev',
        npm_package_name: '@emdash/emdash-desktop',
        NX_TASK_TARGET_TARGET: 'dev',
        NX_NO_CLOUD: 'true',
        PNPM_HOME: '/home/test/.local/share/pnpm',
        PNPM_PACKAGE_NAME: '@emdash/emdash-desktop',
        DISABLE_AUTO_UPDATE: 'true',
      })
    ).toEqual({
      HOME: '/home/test',
      PATH: '/usr/bin',
      SSH_AUTH_SOCK: '/tmp/agent.sock',
      CUSTOM_USER_VALUE: 'kept',
      NX_NO_CLOUD: 'true',
      PNPM_HOME: '/home/test/.local/share/pnpm',
    });
  });
});
