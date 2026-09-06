import path from 'node:path';
import { defineWireComponent } from '@emdash/wire/worker';
import { z } from 'zod';
import { hostSettingsContract } from '../api/contract';
import { createHostSettingsController } from './api/controller';
import { HostSettingsRuntime } from './runtime';

export const hostSettingsComponentConfigSchema = z.object({
  settingsPath: z
    .string()
    .min(1)
    .refine((value) => path.isAbsolute(value), {
      message: 'Host settings path must be absolute',
    }),
});

/** The host-settings worker: sole writer of the host's settings file. */
export const hostSettingsComponent = defineWireComponent({
  id: 'host-settings',
  contract: hostSettingsContract,
  requirements: {},
  configSchema: hostSettingsComponentConfigSchema,
  create: ({ config, instance, logger, scope }) => {
    const runtime = new HostSettingsRuntime({ settingsPath: config.settingsPath, logger });
    scope.add(() => runtime.dispose());
    return instance({
      scope,
      controller: createHostSettingsController(runtime),
    });
  },
});
