import { z } from 'zod';
import { formatHostRef, parseHostRef } from './ref';
import type { HostRef } from './types';

export const hostTypeSchema = z.enum(['local', 'remote']);

export const hostRefSchema = z
  .object({
    type: hostTypeSchema,
    id: z
      .string()
      .min(1)
      .refine((id) => !id.includes('\0'), 'Host id must not contain a null byte'),
  })
  .transform((ref) => ref as HostRef);

export const serializedHostRefSchema = z.string().transform((value, context) => {
  try {
    return formatHostRef(parseHostRef(value));
  } catch (error) {
    context.addIssue({
      code: 'custom',
      message: error instanceof Error ? error.message : 'Invalid serialized host ref',
    });
    return z.NEVER;
  }
});

export type HostRefInput = z.input<typeof hostRefSchema>;
export type HostRefOutput = z.output<typeof hostRefSchema>;
