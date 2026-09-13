import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';

export type ISessionsBehavior = {
  /** Return true when a stored provider session id looks valid and should be used for resume. */
  validateSessionId?(id: string): boolean;
};

export const sessionsCapability = definePluginCapability<ISessionsBehavior>()(
  'sessions',
  z.object({
    kind: z.enum(['resumable', 'stateless']),
  })
);
