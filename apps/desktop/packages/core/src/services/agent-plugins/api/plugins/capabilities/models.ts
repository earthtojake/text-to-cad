import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';

export const modelOptionSchema = z.object({
  name: z.string(),
  description: z.string().optional(),
  modelFeatures: z
    .object({
      contextWindowSize: z.number().optional(),
      speed: z.number().min(1).max(5).optional(),
      intelligence: z.number().min(1).max(5).optional(),
    })
    .optional(),
});

/**
 * ModelsDescriptor describes the models that an agent supports.
 *
 * kind: 'selectable' — the user can pick a model; modelOptions maps model ids to metadata
 * kind: 'none'       — the agent does not expose model selection
 */
export const modelsCapability = definePluginCapability()(
  'models',
  z.discriminatedUnion('kind', [
    z.object({
      kind: z.literal('selectable'),
      modelOptions: z.record(z.string(), modelOptionSchema),
    }),
    z.object({ kind: z.literal('none') }),
  ]),
  { kind: 'none' }
);
