import { describe, expect, it } from 'vitest';
import { workspaceRegistryWorkerSpec, type WorkspaceRegistryWorkerSpecInput } from './worker-spec';

describe('workspaceRegistryWorkerSpec', () => {
  it('keeps default restart for the durable index with a 3s shutdown grace', () => {
    const env = { PATH: '/usr/bin' };
    const [component, options] = workspaceRegistryWorkerSpec({
      executable: '/w/workspace-registry.mjs',
      env,
      dependencies: {} as WorkspaceRegistryWorkerSpecInput['dependencies'],
      databasePath: '/data/workspace-registry.db',
    });
    expect(component.id).toBe('workspace-registry');
    expect(options.name).toBe('workspace-registry');
    expect(options.env).toBe(env);
    expect(component.requirements).toHaveProperty('userEnv');
    expect(options.supervision).toBeUndefined();
    expect(options.shutdownGraceMs).toBe(3_000);
    expect(component.configSchema.parse(options.config)).toEqual({
      databasePath: '/data/workspace-registry.db',
    });
  });
});
