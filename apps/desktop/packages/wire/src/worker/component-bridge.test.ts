import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { connect } from '../api/connect';
import { defineContract, procedure } from '../api/define';
import { client } from '../rpc/client';
import { createController } from '../rpc/controller';
import { FakeWorkerProcess } from '../testing';
import { defineWireComponent, requireContract } from './component';
import { setupComponentWorkerGeneration } from './component-bridge';
import { parentPortChannelTransport } from './component-protocol';

const api = defineContract({
  ping: procedure({ input: z.string(), output: z.string() }),
});

const dependencyApi = defineContract({
  suffix: procedure({ input: z.string(), output: z.string() }),
});

describe('setupComponentWorkerGeneration', () => {
  it('serves dependency channels once for repeated bootstrap requests', async () => {
    const scope = createScope({ label: 'component-bridge-test' });
    const process = new FakeWorkerProcess({ entry: 'worker' });
    const component = defineWireComponent({
      id: 'demo',
      contract: api,
      requirements: {
        dependency: requireContract(dependencyApi),
      },
      configSchema: z.object({}),
      create: ({ instance, scope }) =>
        instance({
          scope,
          controller: createController(api, {
            ping: (input) => input,
          }),
        }),
    });
    let calls = 0;
    const dependency = createController(dependencyApi, {
      suffix: (input) => {
        calls += 1;
        return `dep:${input}`;
      },
    });

    setupComponentWorkerGeneration({
      component,
      dependencies: { dependency },
      config: {},
      process,
      scope,
    });

    process.childPort.send({
      kind: 'wire-component-bootstrap',
      event: 'request',
      componentId: 'demo',
    });
    process.childPort.send({
      kind: 'wire-component-bootstrap',
      event: 'request',
      componentId: 'demo',
    });

    expect(process.parentMessages).toEqual([
      {
        kind: 'wire-component-bootstrap',
        event: 'ready',
        componentId: 'demo',
        config: {},
        dependencies: {
          dependency: { kind: 'contract', channel: 'dep:dependency' },
        },
      },
      {
        kind: 'wire-component-bootstrap',
        event: 'ready',
        componentId: 'demo',
        config: {},
        dependencies: {
          dependency: { kind: 'contract', channel: 'dep:dependency' },
        },
      },
    ]);

    const dependencyClient = client(
      dependencyApi,
      connect(parentPortChannelTransport(process.childPort, 'dep:dependency'))
    );

    await expect(dependencyClient.suffix('one')).resolves.toBe('dep:one');
    expect(calls).toBe(1);

    await scope.dispose();
  });
});
