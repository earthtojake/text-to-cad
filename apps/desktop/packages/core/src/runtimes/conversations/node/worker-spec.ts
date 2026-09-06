import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import { conversationsComponent, type conversationsComponentConfigSchema } from './component';

type ConversationsWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof conversationsComponent)['requirements'],
  z.infer<typeof conversationsComponentConfigSchema>
>;

export type ConversationsWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
  databasePath: string;
};

/**
 * Spawn spec for the conversations index worker. The index depends on nothing and
 * spawns first (spec §3.4); the session runtimes report into it, so their spawns
 * chain on its readiness. Default supervision (restart on failure) is deliberate:
 * a durable index should come back. The 3s shutdown grace lets it close its
 * database cleanly before the host escalates.
 */
export function conversationsWorkerSpec(
  input: ConversationsWorkerSpecInput
): readonly [typeof conversationsComponent, ConversationsWorkerOptions] {
  return [
    conversationsComponent,
    {
      name: 'conversations',
      executable: input.executable,
      env: input.env,
      dependencies: {},
      config: { databasePath: input.databasePath },
      shutdownGraceMs: 3_000,
    },
  ];
}
