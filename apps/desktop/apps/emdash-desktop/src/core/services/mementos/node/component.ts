import path from 'node:path';
import { defineWireComponent } from '@emdash/wire/worker';
import { z } from 'zod';
import { mementosWireContract } from '@core/primitives/mementos/api';
import { MementoService } from './memento-service';
import { MementoPersistenceService } from './persistence';
import { createMementosWireController } from './wire-controller';

const sweepPolicySchema = z.object({
  mementoId: z.string().min(1),
  maxAge: z.number().int().nonnegative(),
  maxEntries: z.number().int().nonnegative(),
});

export const mementosComponentConfigSchema = z.object({
  databasePath: z
    .string()
    .min(1)
    .refine((value) => value === ':memory:' || path.isAbsolute(value), {
      message: 'Mementos database path must be absolute or :memory:',
    }),
  sweepPolicies: z.array(sweepPolicySchema).default([]),
});

export type MementosComponentConfig = z.infer<typeof mementosComponentConfigSchema>;

export const mementosComponent = defineWireComponent({
  id: 'mementos',
  contract: mementosWireContract,
  requirements: {},
  configSchema: mementosComponentConfigSchema,
  create: ({ config, instance, logger, scope }) => {
    const service = new MementoService({
      persistence: MementoPersistenceService.open(config.databasePath),
      scope,
    });
    try {
      service.sweep(config.sweepPolicies);
    } catch (error) {
      logger.error('Memento retention sweep failed', { error: String(error) });
    }
    return instance({
      scope,
      controller: createMementosWireController(service),
    });
  },
});
