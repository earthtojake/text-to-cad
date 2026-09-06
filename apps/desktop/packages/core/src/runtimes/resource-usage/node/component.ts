import { err, ok } from '@emdash/shared';
import { createController } from '@emdash/wire/rpc';
import { defineWireComponent } from '@emdash/wire/worker';
import { z } from 'zod';
import { resourceUsageContract } from '#runtimes/resource-usage/api';
import { ResourceUsageRuntime } from './resource-usage-runtime';

export const resourceUsageComponent = defineWireComponent({
  id: 'resource-usage',
  contract: resourceUsageContract,
  requirements: {},
  configSchema: z.object({}),
  create: ({ instance, scope }) => {
    const runtime = new ResourceUsageRuntime();
    return instance({
      scope,
      controller: createController(resourceUsageContract, {
        sample: async () => {
          try {
            return ok(await runtime.sample());
          } catch (error) {
            return err({
              type: 'sample-failed',
              message: error instanceof Error ? error.message : String(error),
            });
          }
        },
      }),
    });
  },
});
