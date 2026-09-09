import { describe, expect, it } from 'vitest';
import { createUserShellEnvController } from '#services/shell-env/node';
import { scriptsWorkerSpec } from './worker-spec';

describe('scriptsWorkerSpec', () => {
  it('keeps the worker process env separate from the user shell env', () => {
    const env = { ELECTRON_RUN_AS_NODE: '1', NODE_ENV: 'production' };
    const userEnv = createUserShellEnvController(async () => ({
      PATH: '/user/bin',
      USER_VALUE: 'kept',
    }));

    const [component, options] = scriptsWorkerSpec({
      executable: '/w/scripts.mjs',
      env,
      userEnv,
    });

    expect(component.id).toBe('scripts');
    expect(options.env).toBe(env);
    expect(options.dependencies.userEnv).toBe(userEnv);
    expect(component.configSchema.parse(options.config)).toEqual({});
  });
});
