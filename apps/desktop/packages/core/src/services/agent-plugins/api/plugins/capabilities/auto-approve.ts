import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';

/**
 * autoApproveDescriptor is used to describe the auto-approve that an agent supports.
 * @param kind - The kind of auto-approve descriptor.
 * @param kind: 'supported' - The agent supports auto-approve.
 * @param kind: 'none' - The agent does not support auto-approve.
 */
export const autoApproveCapability = definePluginCapability()(
  'auto-approve',
  z.object({
    kind: z.enum(['supported', 'none']),
  }),
  { kind: 'none' }
);
