import { hostRefSchema } from '@emdash/core/primitives/host/api';
import { runtimeResolveErrorSchema } from '@emdash/core/primitives/runtime-resolution/api';
import { z } from 'zod';

export const PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE = 'This action requires live Project access.';

const projectAttachmentSpecificErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('project-missing'), projectId: z.string() }),
  z.object({
    type: z.literal('attachment-unavailable'),
    host: hostRefSchema,
    phase: z.enum(['waiting', 'attaching']),
  }),
  z.object({ type: z.literal('repository-missing'), path: z.string() }),
  z.object({
    type: z.literal('repository-unavailable'),
    path: z.string(),
    message: z.string(),
  }),
  z.object({
    type: z.literal('unexpected'),
    stage: z.enum(['repository-stat', 'session-open']),
    message: z.string(),
  }),
]);

export const projectAttachmentErrorSchema = z.union([
  runtimeResolveErrorSchema,
  projectAttachmentSpecificErrorSchema,
]);

export const projectAttachmentStateSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('absent'),
    lastFailure: projectAttachmentErrorSchema.optional(),
    attemptedHostGeneration: z.number().int().positive().optional(),
  }),
  z.object({
    kind: z.literal('attaching'),
    hostGeneration: z.number().int().positive(),
    attemptId: z.string(),
  }),
  z.object({
    kind: z.literal('attached'),
    establishedHostGeneration: z.number().int().positive(),
  }),
]);

export type ProjectAttachmentError = z.output<typeof projectAttachmentErrorSchema>;
export type ProjectAttachmentState = z.output<typeof projectAttachmentStateSchema>;

export type ProjectRecoveryRequestError = {
  type: 'project-missing';
  projectId: string;
};

export type AttachmentInvalidationCause =
  | 'deletion'
  | 'relink'
  | 'repository-changed'
  | 'retry'
  | 'owner-released'
  | 'shutdown';
