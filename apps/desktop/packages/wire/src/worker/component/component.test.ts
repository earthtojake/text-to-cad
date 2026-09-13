import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { Controller } from '../../api/controller';
import { defineContract, procedure } from '../../api/define';
import { createController } from '../../rpc/controller';
import { defineWireComponent } from './define';
import { requireContract } from './requirements';

const greetingContract = defineContract({
  greet: procedure({ input: z.object({ name: z.string() }), output: z.string() }),
});

describe('defineWireComponent', () => {
  it('creates an in-process instance with a typed client', async () => {
    const scope = createScope({ label: 'test' });
    let disposed = false;
    const component = defineWireComponent({
      id: 'greeter',
      contract: greetingContract,
      requirements: {},
      configSchema: z.object({ prefix: z.string() }),
      create: ({ config, instance, scope }) => {
        scope.add(() => {
          disposed = true;
        });
        return instance({
          scope,
          controller: createController(greetingContract, {
            greet: ({ name }) => `${config.prefix} ${name}`,
          }),
        });
      },
    });

    const created = component.create({
      scope,
      dependencies: {},
      config: { prefix: 'hello' },
    });

    await expect(created.client.greet({ name: 'wire' })).resolves.toBe('hello wire');
    await created.dispose();
    expect(disposed).toBe(true);
  });

  it('disposes component resources when the parent scope is disposed', async () => {
    const scope = createScope({ label: 'test' });
    let disposed = false;
    const component = defineWireComponent({
      id: 'greeter',
      contract: greetingContract,
      requirements: {},
      configSchema: z.object({ prefix: z.string() }),
      create: ({ instance, scope }) => {
        scope.add(() => {
          disposed = true;
        });
        return instance({
          scope,
          controller: greeterController(),
        });
      },
    });

    component.create({
      scope,
      dependencies: {},
      config: { prefix: 'hello' },
    });

    await expect(withTimeout(scope.dispose(), 100)).resolves.toBeUndefined();
    expect(disposed).toBe(true);
  });

  it('disposes controller resources once through direct instance disposal', async () => {
    const scope = createScope({ label: 'test' });
    let disposed = 0;
    const component = defineWireComponent({
      id: 'greeter',
      contract: greetingContract,
      requirements: {},
      configSchema: z.object({ prefix: z.string() }),
      create: ({ instance, scope }) =>
        instance({
          scope,
          controller: {
            ...greeterController(),
            async dispose() {
              disposed += 1;
            },
          },
        }),
    });

    const created = component.create({
      scope,
      dependencies: {},
      config: { prefix: 'hello' },
    });

    await created.dispose();
    await created.dispose();
    await scope.dispose();
    expect(disposed).toBe(1);
  });

  it('validates config before construction', () => {
    const scope = createScope({ label: 'test' });
    let constructed = false;
    const component = defineWireComponent({
      id: 'greeter',
      contract: greetingContract,
      requirements: {},
      configSchema: z.object({ prefix: z.string() }),
      create: ({ instance, scope }) => {
        constructed = true;
        return instance({
          scope,
          controller: createController(greetingContract, {
            greet: ({ name }) => name,
          }),
        });
      },
    });

    expect(() =>
      component.create({
        scope,
        dependencies: {},
        config: { prefix: 123 } as never,
      })
    ).toThrow();
    expect(constructed).toBe(false);
  });

  it('requires exact dependency keys', () => {
    const scope = createScope({ label: 'test' });
    const component = defineWireComponent({
      id: 'dependent',
      contract: greetingContract,
      requirements: {
        greeter: requireContract(greetingContract),
      },
      configSchema: z.object({}),
      create: ({ instance, scope }) =>
        instance({
          scope,
          controller: createController(greetingContract, {
            greet: ({ name }) => name,
          }),
        }),
    });

    expect(() =>
      component.create({
        scope,
        dependencies: {} as never,
        config: {},
      })
    ).toThrow(/missing required dependencies/);
  });
});

function greeterController(): Controller {
  return createController(greetingContract, {
    greet: ({ name }) => `hello ${name}`,
  });
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error(`Timed out after ${ms}ms`)), ms);
    }),
  ]);
}
