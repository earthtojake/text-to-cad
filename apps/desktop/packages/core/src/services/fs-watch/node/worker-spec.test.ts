import { describe, expect, it } from 'vitest';
import { fsWatchWorkerSpec } from './worker-spec';

const env = { PATH: '/usr/bin' };

describe('fsWatchWorkerSpec', () => {
  it('produces the fs-watch spec with default supervision and empty config', () => {
    const [component, options] = fsWatchWorkerSpec({ executable: '/w/fs-watch.mjs', env });
    expect(component.id).toBe('fs-watch');
    expect(options.name).toBe('fs-watch');
    expect(options.executable).toBe('/w/fs-watch.mjs');
    expect(options.env).toBe(env);
    expect(options.supervision).toBeUndefined();
    expect(options.shutdownGraceMs).toBeUndefined();
    expect(component.configSchema.parse(options.config)).toEqual({});
  });
});
