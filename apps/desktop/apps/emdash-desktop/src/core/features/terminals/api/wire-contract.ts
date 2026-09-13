import { hostRefSchema } from '@emdash/core/primitives/host/api';
import {
  terminalShellAvailabilityListSchema,
  terminalShellIdSchema,
} from '@emdash/core/primitives/terminal-shell/api';
import { terminalErrorSchema, terminalSizeSchema } from '@emdash/core/runtimes/terminals/api';
import { runtimeResolveErrorSchema } from '@emdash/core/services/runtime-broker/api';
import { defineContract, fallible, liveLog } from '@emdash/wire/rpc';
import { z } from 'zod';
import { projectAttachmentErrorSchema } from '@core/features/projects/api/attachments';

export const terminalRecordSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  taskId: z.string(),
  ssh: z.boolean().optional(),
  shellId: terminalShellIdSchema,
  name: z.string(),
});

export const terminalCreateInputSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  taskId: z.string(),
  name: z.string(),
  shell: terminalShellIdSchema.optional(),
  initialSize: terminalSizeSchema.optional(),
});

export const terminalTaskInputSchema = z.object({
  projectId: z.string(),
  taskId: z.string(),
});

export const terminalDeleteInputSchema = terminalTaskInputSchema.extend({
  terminalId: z.string(),
});

export const terminalHydrateInputSchema = terminalDeleteInputSchema.extend({
  initialSize: terminalSizeSchema.optional(),
});

export const terminalRenameInputSchema = z.object({
  terminalId: z.string(),
  name: z.string(),
});

export const terminalHydrateResultSchema = z.object({
  key: z.object({
    workspaceId: z.string(),
    terminalId: z.string(),
  }),
});

export const terminalCreateResultSchema = z.object({
  terminal: terminalRecordSchema,
  key: terminalHydrateResultSchema.shape.key,
});

export const terminalRuntimeKeySchema = terminalHydrateResultSchema.shape.key;

export const terminalRuntimeDataInputSchema = terminalRuntimeKeySchema.extend({
  data: z.string(),
});

export const terminalRuntimeResizeInputSchema = terminalRuntimeKeySchema.merge(terminalSizeSchema);

export const terminalShellAvailabilityInputSchema = z.object({
  host: hostRefSchema,
});

/** Failures the desktop slice itself produces while resolving terminal context. */
export const terminalSliceContextErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('missing-terminal'), message: z.string() }),
  z.object({ type: z.literal('missing-task'), message: z.string() }),
  z.object({ type: z.literal('missing-workspace'), message: z.string() }),
  z.object({ type: z.literal('missing-project'), message: z.string() }),
  /** Catch-all for unexpected wire failures surfaced by the slice. */
  z.object({ type: z.literal('terminal-wire-error'), message: z.string() }),
]);
export type TerminalSliceContextError = z.infer<typeof terminalSliceContextErrorSchema>;

export const terminalSliceErrorSchema = z.union([
  projectAttachmentErrorSchema,
  runtimeResolveErrorSchema,
  terminalErrorSchema,
  terminalSliceContextErrorSchema,
]);

export const terminalsDomain = 'terminals' as const;

export const terminalsContract = defineContract({
  list: fallible({
    input: terminalTaskInputSchema,
    data: z.array(terminalRecordSchema),
    error: terminalSliceErrorSchema,
  }),
  create: fallible({
    input: terminalCreateInputSchema,
    data: terminalCreateResultSchema,
    error: terminalSliceErrorSchema,
  }),
  delete: fallible({
    input: terminalDeleteInputSchema,
    data: z.void(),
    error: terminalSliceErrorSchema,
  }),
  rename: fallible({
    input: terminalRenameInputSchema,
    data: z.void(),
    error: terminalSliceErrorSchema,
  }),
  hydrate: fallible({
    input: terminalHydrateInputSchema,
    data: terminalHydrateResultSchema,
    error: terminalSliceErrorSchema,
  }),
  getShellAvailability: fallible({
    input: terminalShellAvailabilityInputSchema,
    data: terminalShellAvailabilityListSchema,
    error: terminalSliceErrorSchema,
  }),
  output: liveLog({
    key: terminalRuntimeKeySchema,
  }),
  sendInput: fallible({
    input: terminalRuntimeDataInputSchema,
    data: z.void(),
    error: terminalSliceErrorSchema,
  }),
  resize: fallible({
    input: terminalRuntimeResizeInputSchema,
    data: z.void(),
    error: terminalSliceErrorSchema,
  }),
  kill: fallible({
    input: terminalRuntimeKeySchema,
    data: z.void(),
    error: terminalSliceErrorSchema,
  }),
});

export type TerminalsContract = typeof terminalsContract;
export type TerminalCreateResult = z.infer<typeof terminalCreateResultSchema>;
export type TerminalHydrateResult = z.infer<typeof terminalHydrateResultSchema>;
export type TerminalRuntimeKey = z.infer<typeof terminalRuntimeKeySchema>;
export type TerminalSliceError = z.infer<typeof terminalSliceErrorSchema>;
