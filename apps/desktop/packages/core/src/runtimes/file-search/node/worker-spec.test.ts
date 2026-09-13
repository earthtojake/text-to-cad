import { describe, expect, it } from 'vitest';
import { fileSearchWorkerSpec, type FileSearchWorkerSpecInput } from './worker-spec';

const env = { PATH: '/usr/bin' };
const dependencies = {} as FileSearchWorkerSpecInput['dependencies'];

describe('fileSearchWorkerSpec', () => {
  it('includes ripgrepPath when provided', () => {
    const [component, options] = fileSearchWorkerSpec({
      executable: '/w/file-search.mjs',
      env,
      dependencies,
      databasePath: '/data/file-search.db',
      ripgrepPath: '/opt/bin/rg',
    });
    expect(component.id).toBe('file-search');
    expect(options.name).toBe('file-search');
    expect(options.env).toBe(env);
    expect(component.requirements).toHaveProperty('userEnv');
    expect(component.configSchema.parse(options.config)).toEqual({
      databasePath: '/data/file-search.db',
      ripgrepPath: '/opt/bin/rg',
    });
  });

  it('omits ripgrepPath when absent', () => {
    const [component, options] = fileSearchWorkerSpec({
      executable: '/w/file-search.mjs',
      env,
      dependencies,
      databasePath: '/data/file-search.db',
    });
    expect(component.configSchema.parse(options.config)).toEqual({
      databasePath: '/data/file-search.db',
    });
  });
});
