import path from 'node:path';
import { defineWireComponent } from '@emdash/wire/worker';
import { z } from 'zod';
import { conversationsContract } from '../api';
import { createConversationsController } from './api/controller';
import { conversationsStore } from './persistence/store';
import { ConversationsRuntime } from './runtime';

export const conversationsComponentConfigSchema = z.object({
  databasePath: z
    .string()
    .min(1)
    .refine((value) => value === ':memory:' || path.isAbsolute(value), {
      message: 'Conversations database path must be absolute or :memory:',
    }),
});

/**
 * The dedicated conversations index worker (spec §3.4): depends on nothing, spawns first,
 * and owns `conversations.db` exclusively (conv.sole-writer). Session runtimes report into
 * it; it never reaches into them.
 */
export const conversationsComponent = defineWireComponent({
  id: 'conversations',
  contract: conversationsContract,
  requirements: {},
  configSchema: conversationsComponentConfigSchema,
  create: ({ config, instance, logger, scope }) => {
    const handle = conversationsStore.open(config.databasePath);
    scope.add(() => handle.close());

    const runtime = new ConversationsRuntime({ handle, logger });
    scope.add(() => runtime.dispose());

    return instance({
      scope,
      controller: createConversationsController(runtime),
    });
  },
});
