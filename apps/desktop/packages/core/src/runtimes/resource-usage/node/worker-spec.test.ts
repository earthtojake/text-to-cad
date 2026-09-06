import { describe, expect, it } from 'vitest';
import { resourceUsageWorkerSpec } from './worker-spec';

describe('resourceUsageWorkerSpec', () => {
  it('produces the resource-usage spec with default supervision and empty config', () => {
    const env = { PATH: '/usr/bin' };
    const [component, options] = resourceUsageWorkerSpec({
      executable: '/w/resource-usage.mjs',
      env,
    });
    expect(component.id).toBe('resource-usage');
    expect(options.name).toBe('resource-usage');
    expect(options.env).toBe(env);
    expect(options.supervision).toBeUndefined();
    expect(options.shutdownGraceMs).toBeUndefined();
    expect(component.configSchema.parse(options.config)).toEqual({});
  });
});
