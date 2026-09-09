import { describe, expect, it } from 'vitest';
import { filesWorkerSpec, type FilesWorkerSpecInput } from './worker-spec';

const env = { PATH: '/usr/bin' };
const dependencies = {} as FilesWorkerSpecInput['dependencies'];

describe('filesWorkerSpec', () => {
  it('includes watchIgnore when provided', () => {
    const [component, options] = filesWorkerSpec({
      executable: '/w/files.mjs',
      env,
      dependencies,
      watchIgnore: ['**/node_modules/**'],
    });
    expect(component.id).toBe('files');
    expect(options.name).toBe('files');
    expect(options.env).toBe(env);
    expect(component.configSchema.parse(options.config)).toEqual({
      watchIgnore: ['**/node_modules/**'],
    });
  });

  it('omits watchIgnore when absent', () => {
    const [component, options] = filesWorkerSpec({
      executable: '/w/files.mjs',
      env,
      dependencies,
    });
    expect(component.configSchema.parse(options.config)).toEqual({});
  });
});
