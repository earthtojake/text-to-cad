import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';

/**
 * EffortDescriptor is used to describe the efforts that an agent supports.
 * @param kind - The kind of effort descriptor.
 * @param effortOptions - The efforts that the agent supports keyed by the effortId.
 * @param kind: 'selectable' - The agent supports selecting an effort.
 * @param kind: 'none' - The agent does not support selecting an effort.
 */
export const effortCapability = definePluginCapability()(
  'effort',
  z.discriminatedUnion('kind', [
    z.object({
      kind: z.literal('selectable'),
      effortOptions: z.record(
        z.string(),
        z.object({
          label: z.string(),
          level: z.number(),
        })
      ),
    }),
    z.object({
      kind: z.literal('none'),
    }),
  ]),
  { kind: 'none' }
);
