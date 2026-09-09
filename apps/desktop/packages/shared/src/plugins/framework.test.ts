import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { definePluginCapability } from './capability';
import { createPluginFramework } from './framework';

describe('createPluginFramework', () => {
  const executableCapability = definePluginCapability<{
    run(): string;
  }>()(
    'executable',
    z.discriminatedUnion('kind', [
      z.object({ kind: z.literal('none') }),
      z.object({ kind: z.literal('supported') }),
    ]),
    { kind: 'none' },
    {
      requiresBehavior: (descriptor) => descriptor.kind === 'supported',
    }
  );

  const metadataSchema = z.object({
    id: z.string(),
  });

  const { definePlugin, registerPluginBehavior } = createPluginFramework(
    { executable: executableCapability },
    metadataSchema,
    {}
  );

  it('registers behavior when a capability requires it', () => {
    const plugin = definePlugin({ id: 'example' }, { executable: { kind: 'supported' } }, {});

    const provider = registerPluginBehavior(plugin, {
      executable: {
        run: () => 'ok',
      },
    });

    expect(provider.behavior.executable?.run()).toBe('ok');
  });

  it('throws when a declared capability requires missing behavior', () => {
    const plugin = definePlugin({ id: 'example' }, { executable: { kind: 'supported' } }, {});

    expect(() => registerPluginBehavior(plugin, {})).toThrow(
      "Plugin 'example' declares capability 'executable' that requires behavior"
    );
  });

  it('allows missing behavior when the capability does not require it', () => {
    const plugin = definePlugin({ id: 'example' }, { executable: { kind: 'none' } }, {});

    expect(registerPluginBehavior(plugin, {}).behavior.executable).toBeUndefined();
  });
});
