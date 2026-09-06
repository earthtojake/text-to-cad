import { describe, expect, it } from 'vitest';
import { conversationsWorkerSpec } from './worker-spec';

describe('conversationsWorkerSpec', () => {
  it('keeps default restart for the durable index with a 3s shutdown grace', () => {
    const env = { PATH: '/usr/bin' };
    const [component, options] = conversationsWorkerSpec({
      executable: '/w/conversations.mjs',
      env,
      databasePath: '/data/conversations.db',
    });
    expect(component.id).toBe('conversations');
    expect(options.name).toBe('conversations');
    expect(options.executable).toBe('/w/conversations.mjs');
    expect(options.env).toBe(env);
    expect(options.supervision).toBeUndefined();
    expect(options.shutdownGraceMs).toBe(3_000);
    expect(component.configSchema.parse(options.config)).toEqual({
      databasePath: '/data/conversations.db',
    });
  });
});
